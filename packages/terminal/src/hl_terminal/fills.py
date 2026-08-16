from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hl_client.markets import resolve_market
from rich.console import Console
from rich.table import Table

from hl_terminal.sizing import format_pnl, format_usd, position_coin_symbol


def fill_matches_coin(fill: dict[str, Any], coin: str | None) -> bool:
    if coin is None:
        return True
    fill_coin = str(fill["coin"])
    needle = coin.strip()
    try:
        resolved = resolve_market(needle).coin
    except ValueError:
        resolved = needle.upper()
    if fill_coin == resolved:
        return True
    return fill_coin.split(":")[-1].upper() == resolved.split(":")[-1].upper()


def filter_fills(
    fills: list[dict[str, Any]],
    *,
    coin: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    filtered = [fill for fill in fills if fill_matches_coin(fill, coin)]
    if limit is not None:
        return filtered[:limit]
    return filtered


def format_fill_time(time_ms: int) -> str:
    return datetime.fromtimestamp(time_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M")


def format_fill_size(fill: dict[str, Any]) -> str:
    px = float(fill["px"])
    sz = float(fill["sz"])
    coin_symbol = position_coin_symbol(str(fill["coin"]))
    return f"{format_usd(px * sz)}\n[dim]{sz:g} {coin_symbol}[/dim]"


def format_fill_closed_pnl(fill: dict[str, Any]) -> str:
    closed_pnl = float(fill.get("closedPnl", 0))
    if abs(closed_pnl) < 1e-12:
        return "-"
    return format_pnl(closed_pnl)


def print_fills_table(
    console: Console,
    fills: list[dict[str, Any]],
    *,
    title: str = "Recent fills",
) -> None:
    table = Table(title=title)
    table.add_column("Time")
    table.add_column("Coin")
    table.add_column("Action")
    table.add_column("Size", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Fee", justify="right")
    table.add_column("Closed PnL", justify="right")

    for fill in fills:
        closed_pnl = float(fill.get("closedPnl", 0))
        pnl_style = None
        if closed_pnl > 0:
            pnl_style = "green"
        elif closed_pnl < 0:
            pnl_style = "red"
        closed_display = format_fill_closed_pnl(fill)
        if pnl_style:
            closed_display = f"[{pnl_style}]{closed_display}[/{pnl_style}]"

        table.add_row(
            format_fill_time(int(fill["time"])),
            str(fill["coin"]),
            str(fill.get("dir", fill["side"])),
            format_fill_size(fill),
            format_usd(float(fill["px"])),
            format_usd(float(fill.get("fee", 0))),
            closed_display,
        )

    console.print()
    console.print(table)
