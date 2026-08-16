from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import typer
from hl_client import (
    HyperliquidClient,
    generate_wallet,
    normalize_eth_address,
    save_wallet_file,
    wallet_from_private_key,
)
from hl_client.exceptions import HyperliquidClientError, TradingNotConfiguredError
from hl_client.tpsl import TpslKind
from hl_client.wallet_store import import_wallet_file_to_db, persist_wallet_to_db
from hl_core import (
    WalletStore,
    WalletStoreError,
    generate_encryption_key,
    get_settings,
    init_database,
    setup_logging,
)
from hl_core.config import Network
from rich.console import Console
from rich.table import Table

from hl_terminal.env_file import resolve_project_path, upsert_env_vars
from hl_terminal.fills import filter_fills, print_fills_table
from hl_terminal.find import (
    fetch_mids_for_markets,
    find_perp_markets,
    format_other_network_hint,
    print_market_search_table,
)
from hl_terminal.historical_cli import historical_app
from hl_terminal.orders import print_open_orders_table
from hl_terminal.responses import print_exchange_result
from hl_terminal.sizing import (
    ResolvedOrderSize,
    format_close_proceeds_display,
    format_pnl,
    format_total_upnl,
    print_position_detail,
    print_positions_table,
    resolve_close_size,
    resolve_order_size,
    total_positions_margin,
    total_positions_notional,
    total_positions_upnl,
)
from hl_terminal.tpsl import format_tpsl_summary, resolve_tpsl_order
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


def _resolve_trade_side(
    *,
    buy: bool,
    sell: bool,
    long: bool,
    short: bool,
    skip_prompts: bool,
) -> bool:
    go_long = buy or long
    go_short = sell or short
    if go_long and go_short:
        raise typer.BadParameter("Choose either long or short, not both.")
    if go_long:
        return True
    if go_short:
        return False
    if skip_prompts:
        raise typer.BadParameter("Specify --long or --short when using -y.")
    choice = typer.prompt("Long or short? [l/s]", default="l").strip().lower()
    if choice in {"l", "long"}:
        return True
    if choice in {"s", "short"}:
        return False
    raise typer.BadParameter("Enter l/long for long or s/short for short.")


def _confirm_trade(client: HyperliquidClient, summary: str, *, yes: bool) -> None:
    _print_network(client)
    if yes:
        return
    if not typer.confirm(f"{summary}. Continue?"):
        console.print("Cancelled.")
        raise typer.Exit(code=0)


def _print_order_result(result: object, *, headline: str | None = None) -> None:
    print_exchange_result(console, result, headline=headline)


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


def _trading_client() -> HyperliquidClient:
    with loading(_loading_message("Connecting to Hyperliquid")):
        return _client()


def _run_trade[T](
    summary: str,
    *,
    yes: bool,
    action: str,
    execute: Callable[[HyperliquidClient], T],
) -> T:
    client = _trading_client()
    _confirm_trade(client, summary, yes=yes)
    with loading(_loading_message(action)):
        return execute(client)


def _run_sized_trade[T](
    coin: str,
    raw_size: str,
    *,
    yes: bool,
    action: str,
    price: float | None = None,
    usd: bool = False,
    coin_units: bool = False,
    notional: bool = False,
    leverage: int | None = None,
    cross: bool = False,
    summary: Callable[[ResolvedOrderSize], str],
    execute: Callable[[HyperliquidClient, float], T],
) -> tuple[T, ResolvedOrderSize]:
    client = _trading_client()
    with loading(_loading_message("Resolving order size")):
        if leverage is not None:
            client.update_leverage(coin, leverage, is_cross=cross)
        resolved = resolve_order_size(
            client,
            coin,
            raw_size,
            price=price,
            usd=usd,
            coin_units=coin_units,
            notional=notional,
            leverage_override=leverage,
        )
    _confirm_trade(client, summary(resolved), yes=yes)
    with loading(_loading_message(action)):
        return execute(client, resolved.coin_size), resolved


def _run_close_trade[T](
    coin: str,
    *,
    raw_size: str | None = None,
    percent: float | None = None,
    yes: bool,
    usd: bool = False,
    coin_units: bool = False,
    execute: Callable[[HyperliquidClient, float], T],
) -> tuple[T, ResolvedOrderSize]:
    client = _trading_client()
    with loading(_loading_message("Resolving close size")):
        resolved = resolve_close_size(
            client,
            coin,
            raw_size,
            percent=percent,
            usd=usd,
            coin_units=coin_units,
        )
    _confirm_trade(
        client,
        f"Market close {resolved.display}",
        yes=yes,
    )
    with loading(_loading_message("Closing position")):
        return execute(client, resolved.coin_size), resolved


def _run_full_close_trade[T](
    coin: str,
    *,
    yes: bool,
    slippage: float,
    execute: Callable[[HyperliquidClient], T],
) -> T:
    client = _trading_client()
    position = client.get_position(coin)
    if position is None:
        raise HyperliquidClientError(f"No open position for {coin.upper()}.")
    summary = (
        "Market close "
        f"{format_close_proceeds_display(position=position, coin_size=abs(position.size))}"
    )
    _confirm_trade(client, summary, yes=yes)
    with loading(_loading_message("Closing position")):
        return execute(client)


def _run_tpsl_trade[T](
    coin: str,
    *,
    kind: TpslKind,
    trigger_px: float,
    limit_px: float | None,
    is_market: bool,
    raw_size: str | None = None,
    percent: float | None = None,
    usd: bool = False,
    coin_units: bool = False,
    yes: bool,
    execute: Callable[[HyperliquidClient, float], T],
) -> tuple[T, ResolvedOrderSize]:
    client = _trading_client()
    with loading(_loading_message("Resolving TP/SL")):
        _position, resolved, _mark = resolve_tpsl_order(
            client,
            coin,
            kind=kind,
            trigger_px=trigger_px,
            raw_size=raw_size,
            percent=percent,
            usd=usd,
            coin_units=coin_units,
        )
    mode = "market" if is_market else "limit"
    summary = format_tpsl_summary(
        kind=kind,
        coin=coin,
        trigger_px=trigger_px,
        limit_px=limit_px,
        mode=mode,
        resolved=resolved,
    )
    _confirm_trade(client, summary, yes=yes)
    with loading(_loading_message("Placing TP/SL")):
        return execute(client, resolved.coin_size), resolved


def _tpsl_options(
    *,
    limit: float | None,
    limit_order: bool,
) -> tuple[float | None, bool]:
    is_market = not limit_order
    return limit, is_market


def _place_tpsl_command(
    *,
    kind: TpslKind,
    coin: str,
    trigger: float,
    limit: float | None,
    limit_order: bool,
    size: str | None,
    percent: float | None,
    usd: bool,
    coin_units: bool,
    yes: bool,
) -> None:
    limit_px, is_market = _tpsl_options(
        limit=limit,
        limit_order=limit_order,
    )
    label = "TP" if kind == "tp" else "SL"
    try:
        result, resolved = _run_tpsl_trade(
            coin,
            kind=kind,
            trigger_px=trigger,
            limit_px=limit_px,
            is_market=is_market,
            raw_size=size,
            percent=percent,
            usd=usd,
            coin_units=coin_units,
            yes=yes,
            execute=lambda client, coin_size: client.place_position_tpsl(
                coin,
                kind=kind,
                trigger_px=trigger,
                size=coin_size,
                limit_px=limit_px,
                is_market=is_market,
            ),
        )
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    mode = "market" if is_market else "limit"
    headline = format_tpsl_summary(
        kind=kind,
        coin=coin,
        trigger_px=trigger,
        limit_px=limit_px,
        mode=mode,
        resolved=resolved,
    )
    _print_order_result(result, headline=headline.replace(f"{label} ", f"{label} placed · ", 1))


_SIZE_HELP = (
    "USD margin by default (30, $30, 30usd). Position size = margin × leverage. "
    "Coin units: --coin or 0.01eth. Size in USD: --notional"
)
_CLOSE_SIZE_HELP = (
    "Partial close size. Percent: 50%. USD position size: 15 or $15. "
    "Coin units: --coin or 0.01eth. Or use --percent / -p."
)
_TPSL_SIZE_HELP = (
    "Size to close on trigger (default: full position). Same formats as close: "
    "50%, 15, --percent / -p, --coin."
)


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


@app.command("find")
def find_markets(
    query: Annotated[str, typer.Argument(help="Search perp markets by substring, e.g. SPCX")],
    dex: Annotated[
        str | None, typer.Option("--dex", help="Limit search to one HIP-3 dex, e.g. xyz")
    ] = None,
    network: Annotated[
        Network | None,
        typer.Option("--network", help="Search a specific network instead of .env default"),
    ] = None,
) -> None:
    """Search perpetual markets across all dexes."""
    settings = get_settings()
    if network is not None:
        settings = settings.model_copy(update={"network": network})

    try:
        with loading(_loading_message("Searching markets")):
            client = HyperliquidClient.readonly(settings)
            matches = find_perp_markets(client, query, dex=dex)
            mids = fetch_mids_for_markets(client, matches) if matches else {}
            other_network_hint = (
                None
                if matches
                else format_other_network_hint(
                    query,
                    current_network=settings.network,
                    dex=dex,
                )
            )
    except (HyperliquidClientError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_network(client)
    if not matches:
        if dex:
            console.print(
                f'No perp markets matching "{query}" on {settings.network} dex {dex}.'
            )
        else:
            console.print(f'No perp markets matching "{query}" on {settings.network}.')
        if other_network_hint:
            console.print(f"[yellow]{other_network_hint}[/yellow]")
            console.print(
                "[dim]Try: hl find "
                f'{query}{f" --dex {dex}" if dex else ""} --network '
                f'{"mainnet" if settings.network == "testnet" else "testnet"}[/dim]'
            )
        return

    title = f'Markets matching "{query}" ({client.settings.network})'
    if dex:
        title = f'Markets matching "{query}" on {dex} ({client.settings.network})'
    print_market_search_table(console, matches, mids=mids, title=title)


@app.command("status")
def status() -> None:
    """Show account summary and open positions."""
    try:
        with loading(_loading_message("Connecting to Hyperliquid")):
            client = _client()
            summary = client.get_account_summary()
            all_time_pnl = client.get_all_time_pnl()
            positions = client.get_positions()
            open_orders = client.get_open_orders()
            mark_prices = (
                {name: float(price) for name, price in client.get_perp_mids().items()}
                if positions
                else {}
            )
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_network(client)
    console.print(f"[bold]Account:[/bold] {client.account_address}")
    console.print(f"[bold]Tradable USDC:[/bold] ${summary.tradable_usdc:,.2f}")
    console.print(
        f"[bold]Total positions:[/bold] ${total_positions_notional(positions):,.2f}"
    )
    console.print(
        f"[bold]Total margin:[/bold] ${total_positions_margin(positions):,.2f}"
    )
    total_upnl = total_positions_upnl(positions)
    upnl_style = "green" if total_upnl >= 0 else "red"
    console.print(
        f"[bold]Total uPnL:[/bold] [{upnl_style}]{format_total_upnl(positions)}[/{upnl_style}]"
    )
    total_pnl_style = "green" if all_time_pnl >= 0 else "red"
    console.print(
        f"[bold]Total PnL:[/bold] [{total_pnl_style}]{format_pnl(all_time_pnl)}[/{total_pnl_style}]"
    )
    if summary.spot_usdc_hold > 0:
        console.print(
            f"[dim]USDC locked (margin & orders):[/dim] "
            f"${summary.spot_usdc_hold:,.2f}"
        )

    if not positions:
        console.print("\nNo open positions.")
    else:
        print_positions_table(console, positions, mark_prices=mark_prices)

    print_open_orders_table(console, open_orders, title="Pending orders", client=client)


@app.command("positions")
def positions() -> None:
    """List open positions."""
    try:
        with loading(_loading_message("Fetching positions")):
            client = _client()
            open_positions = client.get_positions()
            mark_prices = (
                {name: float(price) for name, price in client.get_perp_mids().items()}
                if open_positions
                else {}
            )
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not open_positions:
        console.print("No open positions.")
        return

    print_positions_table(console, open_positions, mark_prices=mark_prices)


@app.command("position")
def position_detail(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    dex: Annotated[
        str | None, typer.Option("--dex", help="HIP-3 dex name when coin has no prefix")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print raw API payload")] = False,
) -> None:
    """Show detailed info for an open position."""
    try:
        with loading(_loading_message("Fetching position")):
            client = _client()
            pos = client.get_position(coin, dex=dex)
            if pos is None:
                from hl_client.markets import resolve_market

                label = resolve_market(coin, dex).coin
                console.print(f"[red]No open position for[/red] {label}")
                raise typer.Exit(code=1)
            mark = client.get_mid(coin, dex=dex)
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_network(client)
    if json_output:
        console.print_json(json.dumps(pos.raw, indent=2))
        return

    print_position_detail(console, pos, mark=mark)


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

    print_open_orders_table(console, open_orders, client=client)


@app.command("fills")
def fills(
    coin: Annotated[
        str | None, typer.Argument(help="Optional coin filter, e.g. ETH")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max fills to show")
    ] = 25,
    json_output: Annotated[bool, typer.Option("--json", help="Print raw API payload")] = False,
) -> None:
    """Show recent trade fills from Hyperliquid (up to 2000)."""
    try:
        with loading(_loading_message("Fetching fills")):
            client = _client()
            raw_fills = client.get_user_fills()
    except HyperliquidClientError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_network(client)
    shown = filter_fills(raw_fills, coin=coin, limit=limit if limit > 0 else None)

    if json_output:
        console.print_json(json.dumps(shown, indent=2))
        return

    if not shown:
        if coin:
            console.print(f"No fills for {coin.upper()}.")
        else:
            console.print("No fills.")
        return

    title = "Recent fills"
    if coin:
        title = f"Recent fills · {coin.upper()}"
    print_fills_table(console, shown, title=title)


@app.command("open")
def open_position(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    size: Annotated[str, typer.Option("--size", "-s", help=_SIZE_HELP)],
    buy: Annotated[bool, typer.Option("--buy", help="Open long (alias: --long)")] = False,
    sell: Annotated[bool, typer.Option("--sell", help="Open short (alias: --short)")] = False,
    long: Annotated[bool, typer.Option("--long", help="Open long")] = False,
    short: Annotated[bool, typer.Option("--short", help="Open short")] = False,
    usd: Annotated[bool, typer.Option("--usd", help="Explicit USD margin amount")] = False,
    coin_units: Annotated[
        bool, typer.Option("--coin", help="Treat --size as coin amount (e.g. 0.01 ETH)")
    ] = False,
    notional: Annotated[
        bool,
        typer.Option("--notional", help="Treat --size as USD position size instead of margin"),
    ] = False,
    leverage: Annotated[
        int | None,
        typer.Option("--leverage", "-x", help="Set coin leverage before opening"),
    ] = None,
    cross: Annotated[
        bool, typer.Option("--cross", help="Use cross margin with --leverage")
    ] = False,
    slippage: Annotated[float, typer.Option("--slippage", help="Max slippage fraction")] = 0.05,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Market-open a position (long or short)."""
    is_buy = _resolve_trade_side(
        buy=buy, sell=sell, long=long, short=short, skip_prompts=yes
    )
    side = "long" if is_buy else "short"

    try:
        result, resolved = _run_sized_trade(
            coin,
            size,
            yes=yes,
            usd=usd,
            coin_units=coin_units,
            notional=notional,
            leverage=leverage,
            cross=cross,
            action="Opening position",
            summary=lambda resolved_size: f"Market {side} {resolved_size.display}",
            execute=lambda client, coin_size: client.market_open(
                coin, is_buy=is_buy, size=coin_size, slippage=slippage
            ),
        )
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(result, headline=f"Market {side} {resolved.display}")


@app.command("limit")
def limit_order(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    price: Annotated[float, typer.Option("--price", "-p", help="Limit price")],
    size: Annotated[str, typer.Option("--size", "-s", help=_SIZE_HELP)],
    buy: Annotated[bool, typer.Option("--buy", help="Buy / long (alias: --long)")] = False,
    sell: Annotated[bool, typer.Option("--sell", help="Sell / short (alias: --short)")] = False,
    long: Annotated[bool, typer.Option("--long", help="Buy / long")] = False,
    short: Annotated[bool, typer.Option("--short", help="Sell / short")] = False,
    usd: Annotated[bool, typer.Option("--usd", help="Explicit USD margin amount")] = False,
    coin_units: Annotated[
        bool, typer.Option("--coin", help="Treat --size as coin amount (e.g. 0.01 ETH)")
    ] = False,
    notional: Annotated[
        bool,
        typer.Option("--notional", help="Treat --size as USD position size instead of margin"),
    ] = False,
    leverage: Annotated[
        int | None,
        typer.Option("--leverage", "-x", help="Set coin leverage before placing"),
    ] = None,
    cross: Annotated[
        bool, typer.Option("--cross", help="Use cross margin with --leverage")
    ] = False,
    tif: Annotated[TimeInForce, typer.Option("--tif", help="Time in force")] = "Gtc",
    reduce_only: Annotated[bool, typer.Option("--reduce-only", help="Reduce-only order")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Place a limit order."""
    is_buy = _resolve_trade_side(
        buy=buy, sell=sell, long=long, short=short, skip_prompts=yes
    )
    side = "long" if is_buy else "short"

    try:
        result, resolved = _run_sized_trade(
            coin,
            size,
            yes=yes,
            usd=usd,
            coin_units=coin_units,
            notional=notional,
            leverage=leverage,
            cross=cross,
            price=price,
            action="Placing limit order",
            summary=lambda resolved_size: (
                f"Limit {side} {resolved_size.display} @ ${price:,.2f} ({tif})"
            ),
            execute=lambda client, coin_size: client.place_limit_order(
                coin,
                is_buy=is_buy,
                size=coin_size,
                price=price,
                tif=tif,
                reduce_only=reduce_only,
            ),
        )
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(
        result,
        headline=f"Limit {side} {resolved.display} @ ${price:,.2f} ({tif})",
    )


@app.command("cancel")
def cancel_order(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    oid: Annotated[int, typer.Argument(help="Order ID to cancel")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Cancel an open order by OID."""
    try:
        result = _run_trade(
            f"Cancel order {oid} on {coin.upper()}",
            yes=yes,
            action="Cancelling order",
            execute=lambda client: client.cancel_order(coin, oid),
        )
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    print_exchange_result(console, result, headline=f"Cancelled order {oid} on {coin.upper()}")


@app.command("leverage")
def leverage(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    value: Annotated[int, typer.Argument(help="Leverage multiplier")],
    cross: Annotated[
        bool, typer.Option("--cross", help="Use cross margin (shared collateral across positions)")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation")] = False,
) -> None:
    """Update leverage for a coin."""
    mode = "cross" if cross else "isolated"
    try:
        result = _run_trade(
            f"Set {coin.upper()} leverage to {value}x ({mode})",
            yes=yes,
            action="Updating leverage",
            execute=lambda client: client.update_leverage(coin, value, is_cross=cross),
        )
    except (HyperliquidClientError, TradingNotConfiguredError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    print_exchange_result(
        console,
        result,
        headline=f"{coin.upper()} leverage set to {value}x ({mode})",
    )


@app.command("tp")
def take_profit(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    trigger: Annotated[float, typer.Option("--trigger", "-t", help="Take-profit trigger price")],
    limit: Annotated[
        float | None,
        typer.Option("--limit", "-l", help="Limit/slippage price once triggered"),
    ] = None,
    size: Annotated[
        str | None, typer.Option("--size", "-s", help=_TPSL_SIZE_HELP)
    ] = None,
    percent: Annotated[
        float | None,
        typer.Option("--percent", "-p", help="Close this percent of the position on trigger"),
    ] = None,
    usd: Annotated[bool, typer.Option("--usd", help="Explicit USD position size to close")] = False,
    coin_units: Annotated[
        bool, typer.Option("--coin", help="Treat --size as coin amount (e.g. 0.01 ETH)")
    ] = False,
    limit_order: Annotated[
        bool, typer.Option("--limit-order", help="Use limit trigger instead of market")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Place a position take-profit order."""
    _place_tpsl_command(
        kind="tp",
        coin=coin,
        trigger=trigger,
        limit=limit,
        limit_order=limit_order,
        size=size,
        percent=percent,
        usd=usd,
        coin_units=coin_units,
        yes=yes,
    )


@app.command("sl")
def stop_loss(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH")],
    trigger: Annotated[float, typer.Option("--trigger", "-t", help="Stop-loss trigger price")],
    limit: Annotated[
        float | None,
        typer.Option("--limit", "-l", help="Limit/slippage price once triggered"),
    ] = None,
    size: Annotated[
        str | None, typer.Option("--size", "-s", help=_TPSL_SIZE_HELP)
    ] = None,
    percent: Annotated[
        float | None,
        typer.Option("--percent", "-p", help="Close this percent of the position on trigger"),
    ] = None,
    usd: Annotated[bool, typer.Option("--usd", help="Explicit USD position size to close")] = False,
    coin_units: Annotated[
        bool, typer.Option("--coin", help="Treat --size as coin amount (e.g. 0.01 ETH)")
    ] = False,
    limit_order: Annotated[
        bool, typer.Option("--limit-order", help="Use limit trigger instead of market")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Place a position stop-loss order."""
    _place_tpsl_command(
        kind="sl",
        coin=coin,
        trigger=trigger,
        limit=limit,
        limit_order=limit_order,
        size=size,
        percent=percent,
        usd=usd,
        coin_units=coin_units,
        yes=yes,
    )


@app.command("close")
def close(
    coin: Annotated[str, typer.Argument(help="Coin symbol to close")],
    size: Annotated[str | None, typer.Option("--size", "-s", help=_CLOSE_SIZE_HELP)] = None,
    percent: Annotated[
        float | None,
        typer.Option("--percent", "-p", help="Close this percent of the position (e.g. 50)"),
    ] = None,
    usd: Annotated[bool, typer.Option("--usd", help="Explicit USD position size to close")] = False,
    coin_units: Annotated[
        bool, typer.Option("--coin", help="Treat --size as coin amount (e.g. 0.01 ETH)")
    ] = False,
    slippage: Annotated[float, typer.Option("--slippage", help="Max slippage fraction")] = 0.05,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Market-close a position (full or partial)."""
    try:
        if size is None and percent is None:
            close_desc = f"Market close {coin.upper()}"
            result = _run_full_close_trade(
                coin,
                yes=yes,
                slippage=slippage,
                execute=lambda client: client.market_close(
                    coin, size=None, slippage=slippage
                ),
            )
            _print_order_result(result, headline=close_desc)
            return

        result, resolved = _run_close_trade(
            coin,
            raw_size=size,
            percent=percent,
            yes=yes,
            usd=usd,
            coin_units=coin_units,
            execute=lambda client, coin_size: client.market_close(
                coin, size=coin_size, slippage=slippage
            ),
        )
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_order_result(result, headline=f"Market close {resolved.display}")


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


@wallet_app.command("import-key")
def wallet_import_key(
    private_key: Annotated[
        str | None,
        typer.Argument(help="Private key (0x...). Omit and use --prompt for hidden input."),
    ] = None,
    prompt: Annotated[
        bool,
        typer.Option("--prompt", "-p", help="Prompt for private key (not echoed)"),
    ] = False,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Save wallet JSON here (mode 600)"),
    ] = None,
    label: Annotated[str | None, typer.Option("--label", help="Optional wallet label")] = None,
    show_key: Annotated[
        bool,
        typer.Option("--show-key", help="Print private key to terminal"),
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite output file")] = False,
    write_env: Annotated[
        bool,
        typer.Option(
            "--write-env",
            help="Write HL_ACCOUNT_ADDRESS and HL_SECRET_KEY to .env",
        ),
    ] = False,
    env_file: Annotated[
        Path,
        typer.Option("--env-file", help="Dotenv file to update (default: .env)"),
    ] = Path(".env"),
) -> None:
    """Import an existing private key and save it as a local wallet file."""
    key_input = private_key
    if key_input is None:
        if prompt:
            key_input = typer.prompt("Private key", hide_input=True)
        else:
            console.print(
                "[red]Error:[/red] Provide a private key argument or use --prompt."
            )
            raise typer.Exit(code=1)

    try:
        wallet = wallet_from_private_key(key_input)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_path = out or Path(f"wallets/imported-{timestamp}.json")
    extra = {"label": label} if label else None

    try:
        saved_path = save_wallet_file(
            output_path,
            wallet,
            kind="evm",
            network=get_settings().network,
            overwrite=force,
            extra=extra,
        )
    except FileExistsError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[green]Wallet imported[/green]")
    console.print(f"[bold]Address:[/bold] {wallet.address}")
    console.print(f"[bold]Saved to:[/bold] {saved_path}")

    if show_key:
        console.print(f"[bold red]Private key:[/bold red] {wallet.private_key_hex}")

    if write_env:
        target_env = resolve_project_path(env_file)
        try:
            updated = upsert_env_vars(
                target_env,
                {
                    "HL_ACCOUNT_ADDRESS": wallet.address,
                    "HL_SECRET_KEY": wallet.private_key_hex,
                },
            )
        except OSError as exc:
            console.print(f"[red]Error updating {target_env}:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(
            f"[green]Updated {target_env}:[/green] {', '.join(updated)}"
        )
    else:
        target_env = resolve_project_path(env_file)
        console.print(
            "[dim]Add to .env or rerun with --write-env to update "
            f"{target_env}[/dim]"
        )

    _persist_wallet_to_db(
        address=wallet.address,
        private_key=wallet.private_key,
        kind="evm",
        network=get_settings().network,
        label=label,
        file_path=saved_path,
        metadata=extra,
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
        client = _trading_client()
        _confirm_trade(client, "Approve new Hyperliquid agent wallet", yes=yes)
        with loading(_loading_message("Approving agent wallet")):
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
        client = _trading_client()
        summary = client.get_account_summary()
        _print_network(client)
        console.print(f"[bold]Withdrawable:[/bold] ${summary.withdrawable:,.2f}")
        if not yes and not typer.confirm(
            f"Withdraw ${amount:,.2f} USDC to {dest}. Continue?"
        ):
            console.print("Cancelled.")
            raise typer.Exit(code=0)
        with loading(_loading_message("Submitting withdrawal")):
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
        result = _run_trade(
            f"Send ${amount:,.2f} USD to {dest} on Hyperliquid",
            yes=yes,
            action="Sending USD",
            execute=lambda client: client.send_usd(amount, dest),
        )
    except (HyperliquidClientError, TradingNotConfiguredError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print_json(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
