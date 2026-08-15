from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

import typer
from hl_core.config import get_settings
from hl_historical import HistoricalTracker, InsufficientDataError, TimestampParseError
from rich.console import Console
from rich.table import Table

from hl_terminal.ui import loading

historical_app = typer.Typer(help="Historical market data and signal verification.")
console = Console()

SideOption = Literal["long", "short"]
IntervalOption = Literal["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d"]


def _tracker() -> HistoricalTracker:
    return HistoricalTracker()


def _loading_message(action: str) -> str:
    return f"{action} ({get_settings().network})..."


@historical_app.command("price")
def historical_price(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH or xyz:SPCX")],
    at: Annotated[
        str,
        typer.Option(
            "--at",
            help="Time (ISO-8601, unix ms, or e.g. '9:35am GMT+1 today')",
        ),
    ],
    interval: Annotated[
        IntervalOption, typer.Option("--interval", help="Candle interval")
    ] = "15m",
    dex: Annotated[
        str | None, typer.Option("--dex", help="HIP-3 dex name, e.g. xyz")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output")] = False,
) -> None:
    """Get the OHLC price for a coin at a specific time."""
    try:
        with loading(_loading_message("Fetching historical price")):
            price = _tracker().get_price_at(coin, at, interval=interval, dex=dex)
    except (InsufficientDataError, TimestampParseError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        console.print_json(json.dumps(price.to_dict(), indent=2))
        return

    console.print(f"[bold]{price.coin}[/bold] @ {price.time.isoformat()}")
    console.print(f"Interval: {price.interval}")
    console.print(f"Open:  {price.open:,.4f}")
    console.print(f"High:  {price.high:,.4f}")
    console.print(f"Low:   {price.low:,.4f}")
    console.print(f"Close: {price.close:,.4f}")


@historical_app.command("analyze")
def historical_analyze(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH or xyz:SPCX")],
    at: Annotated[
        str,
        typer.Option(
            "--at",
            help="Signal time (ISO-8601, unix ms, or e.g. '9:35am GMT+1 today')",
        ),
    ],
    side: Annotated[SideOption, typer.Option("--side", help="Signal direction")],
    entry: Annotated[float | None, typer.Option("--entry", help="Entry price override")] = None,
    interval: Annotated[IntervalOption, typer.Option("--interval", help="Candle interval")] = "1h",
    lookback: Annotated[float, typer.Option("--lookback", help="Hours before signal")] = 1.0,
    forward: Annotated[float, typer.Option("--forward", help="Hours after signal")] = 24.0,
    dex: Annotated[str | None, typer.Option("--dex", help="HIP-3 dex name, e.g. xyz")] = None,
    no_funding: Annotated[bool, typer.Option("--no-funding", help="Skip funding lookup")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output")] = False,
) -> None:
    """Analyze a past signal: MFE, MAE, and final move over a candle window."""
    try:
        with loading(_loading_message("Analyzing signal")):
            result = _tracker().analyze_signal(
                coin,
                at,
                side=side,
                entry_price=entry,
                interval=interval,
                lookback_hours=lookback,
                forward_hours=forward,
                include_funding=not no_funding,
                dex=dex,
            )
    except (InsufficientDataError, TimestampParseError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        payload = result.to_dict()
        if result.funding:
            payload["funding"] = [
                {
                    "time_ms": item.time_ms,
                    "funding_rate": item.funding_rate,
                    "premium": item.premium,
                }
                for item in result.funding
            ]
        console.print_json(json.dumps(payload, indent=2))
        return

    console.print(f"[bold]{result.coin}[/bold] {result.side.upper()} signal analysis")
    console.print(f"Signal time: {result.signal_time.isoformat()}")
    console.print(f"Entry price: {result.entry_price:,.4f}")
    console.print(f"Interval: {result.interval}")
    console.print(
        f"Window: {result.window_start.isoformat()} -> {result.window_end.isoformat()}"
    )
    console.print(f"MFE: [green]{result.mfe_pct:,.2f}%[/green]")
    console.print(f"MAE: [red]{result.mae_pct:,.2f}%[/red]")
    console.print(f"Final move: {result.final_move_pct:,.2f}%")
    console.print(
        f"Range close/high/low: {result.window_close:,.4f} / "
        f"{result.window_high:,.4f} / {result.window_low:,.4f}"
    )
    console.print(f"Candles used: {result.candle_count}")
    console.print(f"Funding records: {len(result.funding)}")


@historical_app.command("candles")
def historical_candles(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH or xyz:SPCX")],
    at: Annotated[
        str,
        typer.Option(
            "--at",
            help="Anchor time (ISO-8601, unix ms, or e.g. '9:35am GMT+1 today')",
        ),
    ],
    interval: Annotated[IntervalOption, typer.Option("--interval", help="Candle interval")] = "1h",
    lookback: Annotated[float, typer.Option("--lookback", help="Hours before anchor")] = 1.0,
    forward: Annotated[float, typer.Option("--forward", help="Hours after anchor")] = 24.0,
    dex: Annotated[str | None, typer.Option("--dex", help="HIP-3 dex name, e.g. xyz")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output")] = False,
) -> None:
    """Fetch candles around a timestamp."""
    try:
        with loading(_loading_message("Fetching candles")):
            window = _tracker().get_candles_around(
                coin,
                at,
                interval=interval,
                lookback_hours=lookback,
                forward_hours=forward,
                dex=dex,
            )
    except (InsufficientDataError, TimestampParseError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "coin": window.coin,
                    "interval": window.interval,
                    "signal_ms": window.signal_ms,
                    "candles": [candle.raw for candle in window.candles],
                },
                indent=2,
            )
        )
        return

    table = Table(title=f"{window.coin} candles ({window.interval})")
    table.add_column("Start (UTC)")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")

    for candle in window.candles:
        start = datetime.fromtimestamp(candle.start_ms / 1000, tz=UTC).isoformat()
        table.add_row(
            start,
            f"{candle.open:,.4f}",
            f"{candle.high:,.4f}",
            f"{candle.low:,.4f}",
            f"{candle.close:,.4f}",
        )

    console.print(table)


@historical_app.command("funding")
def historical_funding(
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. ETH or xyz:SPCX")],
    at: Annotated[
        str,
        typer.Option(
            "--at",
            help="Anchor time (ISO-8601, unix ms, or e.g. '9:35am GMT+1 today')",
        ),
    ],
    lookback: Annotated[float, typer.Option("--lookback", help="Hours before anchor")] = 24.0,
    forward: Annotated[float, typer.Option("--forward", help="Hours after anchor")] = 24.0,
    dex: Annotated[str | None, typer.Option("--dex", help="HIP-3 dex name, e.g. xyz")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output")] = False,
) -> None:
    """Fetch funding history around a timestamp."""
    try:
        with loading(_loading_message("Fetching funding history")):
            funding = _tracker().get_funding_around(
                coin,
                at,
                lookback_hours=lookback,
                forward_hours=forward,
                dex=dex,
            )
    except (TimestampParseError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        console.print_json(
            json.dumps([record.raw for record in funding], indent=2),
        )
        return

    if not funding:
        console.print("No funding records in this window.")
        return

    table = Table(title=f"{coin.upper()} funding")
    table.add_column("Time (UTC)")
    table.add_column("Funding rate", justify="right")
    table.add_column("Premium", justify="right")

    for record in funding:
        when = datetime.fromtimestamp(record.time_ms / 1000, tz=UTC).isoformat()
        table.add_row(when, f"{record.funding_rate:.8f}", f"{record.premium:.8f}")

    console.print(table)
