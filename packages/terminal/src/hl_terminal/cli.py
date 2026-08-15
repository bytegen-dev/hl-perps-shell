from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from hl_client import (
    HyperliquidClient,
    generate_wallet,
    normalize_eth_address,
    save_wallet_file,
)
from hl_client.exceptions import HyperliquidClientError, TradingNotConfiguredError
from hl_client.wallet_store import import_wallet_file_to_db, persist_wallet_to_db
from hl_core import (
    WalletStore,
    WalletStoreError,
    generate_encryption_key,
    get_settings,
    init_database,
    setup_logging,
)
from rich.console import Console
from rich.table import Table

from hl_terminal.historical_cli import historical_app
from hl_terminal.ui import loading

app = typer.Typer(
    name="hl",
    help="Hyperliquid trading terminal for hl-xfgen.",
    no_args_is_help=True,
)
wallet_app = typer.Typer(help="Generate and manage wallets.")
db_app = typer.Typer(help="Local Postgres setup for wallet storage.")
app.add_typer(wallet_app, name="wallet")
app.add_typer(db_app, name="db")
app.add_typer(historical_app, name="historical")
console = Console()

TimeInForce = Literal["Gtc", "Ioc", "Alo"]


def _client(*, readonly: bool = False) -> HyperliquidClient:
    settings = get_settings()
    if readonly:
        return HyperliquidClient.readonly(settings)
    return HyperliquidClient.from_settings(settings)


def _print_network(client: HyperliquidClient) -> None:
    if client.settings.network == "mainnet":
        console.print("[bold red]MAINNET[/bold red] — real funds at risk")
    else:
        console.print(f"[cyan]Network:[/cyan] {client.settings.network}")


def _side_from_flags(*, buy: bool, sell: bool) -> bool:
    if buy == sell:
        raise typer.BadParameter("Specify exactly one of --buy or --sell.")
    return buy


def _confirm_trade(client: HyperliquidClient, summary: str, *, yes: bool) -> None:
    _print_network(client)
    if yes:
        return
    if client.settings.network == "mainnet" and not typer.confirm(f"{summary}. Continue?"):
        console.print("Cancelled.")
        raise typer.Exit(code=0)


def _print_order_result(result: object) -> None:
    if hasattr(result, "raw"):
        console.print_json(json.dumps(result.raw, indent=2))  # type: ignore[union-attr]
    else:
        console.print_json(json.dumps(result, indent=2))


def _persist_wallet_to_db(
    *,
    address: str,
    private_key: str,
    kind: Literal["evm", "agent"],
    network: str | None,
    label: str | None = None,
    master_account: str | None = None,
    file_path: Path,
    metadata: dict[str, object] | None = None,
) -> None:
    from hl_client.types import GeneratedWallet
    from sqlalchemy.exc import SQLAlchemyError

    try:
        persist_wallet_to_db(
            GeneratedWallet(address=address, private_key=private_key),
            kind=kind,
            network=network,
            label=label,
            master_account=master_account,
            file_path=file_path,
            metadata=metadata,
        )
    except (WalletStoreError, ValueError, OSError, SQLAlchemyError) as exc:
        console.print(
            f"[yellow]Wallet file saved, but Postgres backup failed:[/yellow] {exc}\n"
            "[dim]Start Postgres with `docker compose up -d`, set HL_WALLET_ENCRYPTION_KEY "
            "(run `hl db generate-key`), then `hl wallet import` on the saved file.[/dim]"
        )
        return

    console.print("[green]Wallet backed up to local Postgres[/green]")


@app.callback()
def main() -> None:
    setup_logging()


def _loading_message(action: str) -> str:
    return f"{action} ({get_settings().network})..."


@app.command("mids")
def mids(
    coin: Annotated[
        str | None, typer.Argument(help="Optional coin filter, e.g. ETH or xyz:SPCX")
    ] = None,
    dex: Annotated[
        str | None, typer.Option("--dex", help="HIP-3 dex name when coin has no prefix")
    ] = None,
    all_markets: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Include spot (@…) and other non-perp markets (default: perps only)",
        ),
    ] = False,
) -> None:
    """Show mid prices for all coins or a single coin."""
    settings = get_settings()

    with loading(_loading_message("Fetching mid prices")):
        client = HyperliquidClient.readonly(settings)

        if coin:
            try:
                mid = client.get_mid(coin, dex=dex)
            except ValueError as exc:
                console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(code=1) from exc
            if mid is None:
                console.print(f"[red]Coin not found:[/red] {coin}")
                raise typer.Exit(code=1)
            from hl_client.markets import resolve_market

            label = resolve_market(coin, dex).coin
            console.print(f"{label}: {mid}")
            return

        all_mids = client.get_all_mids(dex=dex) if all_markets else client.get_perp_mids(dex=dex)
    title = f"Mids ({client.settings.network})"
    if dex:
        title += f" dex={dex}"
    if not all_markets:
        title += " perps"

    table = Table(title=title)
    table.add_column("Coin", style="cyan")
    table.add_column("Mid", justify="right")

    for name in sorted(all_mids):
        table.add_row(name, all_mids[name])

    console.print(table)


@app.command("status")
def status() -> None:
    """Show account summary and open positions."""
    try:
        with loading(_loading_message("Connecting to Hyperliquid")):
            client = _client()
            summary = client.get_account_summary()
            positions = client.get_positions()
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_network(client)
    console.print(f"[bold]Account:[/bold] {client.account_address}")
    console.print(f"[bold]Account value:[/bold] ${summary.account_value:,.2f}")
    console.print(f"[bold]Margin used:[/bold] ${summary.total_margin_used:,.2f}")
    console.print(f"[bold]Withdrawable:[/bold] ${summary.withdrawable:,.2f}")

    if not positions:
        console.print("\nNo open positions.")
        return

    table = Table(title="Open positions")
    table.add_column("Coin")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("uPnL", justify="right")
    table.add_column("Lev", justify="right")

    for pos in positions:
        entry = f"{pos.entry_px:.4f}" if pos.entry_px is not None else "-"
        table.add_row(
            pos.coin,
            f"{pos.size:,.4f}",
            entry,
            f"{pos.unrealized_pnl:,.2f}",
            f"{pos.leverage_value}x {pos.leverage_type}",
        )

    console.print()
    console.print(table)


@app.command("positions")
def positions() -> None:
    """List open positions."""
    try:
        with loading(_loading_message("Fetching positions")):
            client = _client()
            open_positions = client.get_positions()
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not open_positions:
        console.print("No open positions.")
        return

    console.print_json(json.dumps([p.raw for p in open_positions], indent=2))


@app.command("orders")
def orders() -> None:
    """List open orders."""
    try:
        with loading(_loading_message("Fetching open orders")):
            client = _client()
            open_orders = client.get_open_orders()
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not open_orders:
        console.print("No open orders.")
        return

    table = Table(title="Open orders")
    table.add_column("Coin")
    table.add_column("Side")
    table.add_column("Size", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("OID", justify="right")

    for order in open_orders:
        side = "buy" if order["side"] == "B" else "sell"
        table.add_row(
            order["coin"],
            side,
            order["sz"],
            order["limitPx"],
            str(order["oid"]),
        )

    console.print(table)


@app.command("open")
def open_position(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    size: Annotated[float, typer.Option("--size", "-s", help="Position size")],
    buy: Annotated[bool, typer.Option("--buy", help="Open long")] = False,
    sell: Annotated[bool, typer.Option("--sell", help="Open short")] = False,
    slippage: Annotated[float, typer.Option("--slippage", help="Max slippage fraction")] = 0.05,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Market-open a position (long or short)."""
    is_buy = _side_from_flags(buy=buy, sell=sell)
    side = "long" if is_buy else "short"

    try:
        client = _client()
        _confirm_trade(
            client,
            f"Market open {side} {size} {coin.upper()}",
            yes=yes,
        )
        result = client.market_open(coin, is_buy=is_buy, size=size, slippage=slippage)
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(result)


@app.command("limit")
def limit_order(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    price: Annotated[float, typer.Option("--price", "-p", help="Limit price")],
    size: Annotated[float, typer.Option("--size", "-s", help="Order size")],
    buy: Annotated[bool, typer.Option("--buy", help="Buy / long")] = False,
    sell: Annotated[bool, typer.Option("--sell", help="Sell / short")] = False,
    tif: Annotated[TimeInForce, typer.Option("--tif", help="Time in force")] = "Gtc",
    reduce_only: Annotated[bool, typer.Option("--reduce-only", help="Reduce-only order")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Place a limit order."""
    is_buy = _side_from_flags(buy=buy, sell=sell)
    side = "buy" if is_buy else "sell"

    try:
        client = _client()
        _confirm_trade(
            client,
            f"Limit {side} {size} {coin.upper()} @ {price} ({tif})",
            yes=yes,
        )
        result = client.place_limit_order(
            coin,
            is_buy=is_buy,
            size=size,
            price=price,
            tif=tif,
            reduce_only=reduce_only,
        )
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(result)


@app.command("cancel")
def cancel_order(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    oid: Annotated[int, typer.Argument(help="Order ID to cancel")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Cancel an open order by OID."""
    try:
        client = _client()
        _confirm_trade(client, f"Cancel order {oid} on {coin.upper()}", yes=yes)
        result = client.cancel_order(coin, oid)
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print_json(json.dumps(result, indent=2))


@app.command("leverage")
def leverage(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    value: Annotated[int, typer.Argument(help="Leverage multiplier")],
    isolated: Annotated[bool, typer.Option("--isolated", help="Use isolated margin")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Update leverage for a coin."""
    mode = "isolated" if isolated else "cross"
    try:
        client = _client()
        _confirm_trade(client, f"Set {coin.upper()} leverage to {value}x ({mode})", yes=yes)
        result = client.update_leverage(coin, value, is_cross=not isolated)
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print_json(json.dumps(result, indent=2))


@app.command("close")
def close(
    coin: Annotated[str, typer.Argument(help="Coin symbol to close")],
    size: Annotated[float | None, typer.Option("--size", "-s", help="Partial close size")] = None,
    slippage: Annotated[float, typer.Option("--slippage", help="Max slippage fraction")] = 0.05,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Market-close a position (full or partial)."""
    close_desc = f"Market close {coin.upper()}"
    if size is not None:
        close_desc += f" (size {size})"

    try:
        client = _client()
        _confirm_trade(client, close_desc, yes=yes)
        result = client.market_close(coin, size=size, slippage=slippage)
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(result)


@wallet_app.command("generate")
def wallet_generate(
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Save wallet JSON here (mode 600)"),
    ] = None,
    show_key: Annotated[
        bool,
        typer.Option("--show-key", help="Print private key to terminal"),
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite output file")] = False,
) -> None:
    """Generate a new EVM wallet (private key + address)."""
    wallet = generate_wallet()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_path = out or Path(f"wallets/wallet-{timestamp}.json")

    try:
        saved_path = save_wallet_file(
            output_path,
            wallet,
            kind="evm",
            network=get_settings().network,
            overwrite=force,
        )
    except FileExistsError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[green]Wallet created[/green]")
    console.print(f"[bold]Address:[/bold] {wallet.address}")
    console.print(f"[bold]Saved to:[/bold] {saved_path}")

    if show_key:
        console.print(f"[bold red]Private key:[/bold red] {wallet.private_key_hex}")
    else:
        console.print("Use --show-key to print the private key, or read it from the saved file.")

    _persist_wallet_to_db(
        address=wallet.address,
        private_key=wallet.private_key,
        kind="evm",
        network=get_settings().network,
        file_path=saved_path,
    )
    console.print("[yellow]Keep this file private. Never commit it to git.[/yellow]")


@wallet_app.command("approve-agent")
def wallet_approve_agent(
    name: Annotated[str | None, typer.Option("--name", help="Optional agent label")] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Save approved agent wallet JSON here"),
    ] = None,
    show_key: Annotated[bool, typer.Option("--show-key", help="Print agent private key")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite output file")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Generate and approve a Hyperliquid API/agent wallet for the configured account."""
    try:
        client = _client()
        _confirm_trade(client, "Approve new Hyperliquid agent wallet", yes=yes)
        approved = client.approve_agent_wallet(name)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        output_path = out or Path(f"wallets/agent-{timestamp}.json")
        saved_path = save_wallet_file(
            output_path,
            approved,
            kind="agent",
            network=client.settings.network,
            overwrite=force,
            extra={
                "master_account": client.account_address,
                "approval_result": approved.approval_result,
            },
        )
    except (HyperliquidClientError, TradingNotConfiguredError, FileExistsError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[green]Agent wallet approved[/green]")
    console.print(f"[bold]Master account:[/bold] {client.account_address}")
    console.print(f"[bold]Agent address:[/bold] {approved.address}")
    console.print(f"[bold]Saved to:[/bold] {saved_path}")
    _persist_wallet_to_db(
        address=approved.address,
        private_key=approved.private_key,
        kind="agent",
        network=client.settings.network,
        label=name,
        master_account=client.account_address,
        file_path=saved_path,
        metadata={"approval_result": approved.approval_result},
    )
    console.print(
        "[dim]Set HL_ACCOUNT_ADDRESS to the master account and "
        "HL_SECRET_KEY to the agent key.[/dim]"
    )
    console.print("[yellow]Keep this file private. Never commit it to git.[/yellow]")

    if show_key:
        console.print(f"[bold red]Agent private key:[/bold red] {approved.private_key_hex}")

    console.print_json(json.dumps(approved.approval_result, indent=2))


@wallet_app.command("list")
def wallet_list() -> None:
    """List wallets stored in local Postgres."""
    try:
        store = WalletStore()
        wallets = store.list_wallets()
    except (WalletStoreError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not wallets:
        console.print("No wallets in Postgres yet.")
        return

    table = Table(title="Stored wallets")
    table.add_column("Address")
    table.add_column("Kind")
    table.add_column("Network")
    table.add_column("Label")
    table.add_column("Master")
    table.add_column("Created")

    for wallet in wallets:
        table.add_row(
            wallet.address,
            wallet.kind,
            wallet.network or "-",
            wallet.label or "-",
            wallet.master_account or "-",
            wallet.created_at.isoformat(),
        )

    console.print(table)


@wallet_app.command("import")
def wallet_import(
    path: Annotated[Path, typer.Argument(help="Wallet JSON file to import")],
    label: Annotated[str | None, typer.Option("--label", help="Optional wallet label")] = None,
) -> None:
    """Import a wallet JSON file into local Postgres."""
    try:
        import_wallet_file_to_db(path, label=label)
    except (WalletStoreError, ValueError, FileNotFoundError, OSError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Imported wallet from[/green] {path}")


@db_app.command("init")
def db_init() -> None:
    """Create Postgres tables for wallet storage."""
    try:
        init_database()
    except (WalletStoreError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[green]Postgres schema initialized[/green]")


@db_app.command("generate-key")
def db_generate_key() -> None:
    """Generate a new HL_WALLET_ENCRYPTION_KEY value."""
    key = generate_encryption_key()
    console.print("[bold]Add this to your .env:[/bold]")
    console.print(f"HL_WALLET_ENCRYPTION_KEY={key}")
    console.print(
        "[yellow]Store this key safely. Losing it means losing access to "
        "encrypted wallets.[/yellow]"
    )


@app.command("withdraw")
def withdraw(
    amount: Annotated[float, typer.Argument(help="USDC amount to withdraw")],
    destination: Annotated[str, typer.Argument(help="Destination 0x address (e.g. Arbitrum)")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Withdraw USDC from Hyperliquid to an external address via the bridge."""
    try:
        dest = normalize_eth_address(destination)
        client = _client()
        _confirm_trade(
            client,
            f"Withdraw ${amount:,.2f} USDC to {dest}",
            yes=yes,
        )
        result = client.withdraw_to_arbitrum(amount, dest)
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print_json(json.dumps(result, indent=2))


@app.command("send")
def send_usd(
    amount: Annotated[float, typer.Argument(help="USD amount to send")],
    destination: Annotated[str, typer.Argument(help="Recipient Hyperliquid 0x address")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Send USD to another Hyperliquid account (internal transfer, not bridge withdraw)."""
    try:
        dest = normalize_eth_address(destination)
        client = _client()
        _confirm_trade(
            client,
            f"Send ${amount:,.2f} USD to {dest} on Hyperliquid",
            yes=yes,
        )
        result = client.send_usd(amount, dest)
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print_json(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
