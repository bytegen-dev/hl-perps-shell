from __future__ import annotations

from typing import Any

from hl_client import HyperliquidClient
from hl_client.exceptions import HyperliquidClientError
from rich.console import Console
from rich.table import Table

from hl_terminal.sizing import CoinLeverage, format_order_margin_estimate, get_coin_leverage


def _leverage_cache(
    client: HyperliquidClient,
    orders: list[dict[str, Any]],
) -> dict[str, CoinLeverage | None]:
    cache: dict[str, CoinLeverage | None] = {}
    for coin in {str(order["coin"]) for order in orders}:
        try:
            cache[coin] = get_coin_leverage(client, coin)
        except HyperliquidClientError:
            cache[coin] = None
    return cache


def print_open_orders_table(
    console: Console,
    orders: list[dict[str, Any]],
    *,
    title: str = "Open orders",
    client: HyperliquidClient | None = None,
) -> None:
    if not orders:
        console.print(f"\n{title}: none.")
        return

    leverage_by_coin = _leverage_cache(client, orders) if client is not None else {}

    table = Table(title=title)
    table.add_column("Coin")
    table.add_column("Type")
    table.add_column("Side")
    table.add_column("Size", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Trigger", justify="right")
    if client is not None:
        table.add_column("Lev", justify="right")
        table.add_column("Margin", justify="right")
    table.add_column("OID", justify="right")

    for order in orders:
        side = "buy" if order["side"] == "B" else "sell"
        order_type = str(order.get("orderType", "Limit"))
        if order.get("isPositionTpsl"):
            order_type = f"{order_type} (pos)"
        trigger_px = order.get("triggerPx", "0.0")
        trigger_display = trigger_px if order.get("isTrigger") else "—"
        row = [
            order["coin"],
            order_type,
            side,
            order["sz"],
            order["limitPx"],
            trigger_display,
        ]
        if client is not None:
            coin = str(order["coin"])
            leverage = leverage_by_coin.get(coin)
            row.extend(
                [
                    leverage.label if leverage is not None else "—",
                    format_order_margin_estimate(order, leverage=leverage),
                ]
            )
        row.append(str(order["oid"]))
        table.add_row(*row)

    console.print()
    console.print(table)
    if client is not None:
        console.print("[dim]Lev and margin use current coin settings at fill time.[/dim]")
