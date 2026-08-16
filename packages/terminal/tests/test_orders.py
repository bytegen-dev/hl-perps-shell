from io import StringIO
from unittest.mock import MagicMock

import pytest
from hl_terminal.orders import print_open_orders_table
from hl_terminal.sizing import (
    CoinLeverage,
    format_order_margin_estimate,
    get_coin_leverage,
    resolve_order_size,
)
from rich.console import Console


class _FakeClient:
    def __init__(self, *, leverage: int = 5, leverage_type: str = "cross") -> None:
        self._leverage = leverage
        self._leverage_type = leverage_type

    def get_active_asset_data(self, coin: str, *, dex: str | None = None) -> dict:
        return {"leverage": {"type": self._leverage_type, "value": self._leverage}}

    def get_mid(self, coin: str, *, dex: str | None = None) -> float:
        return 2000.0

    def get_meta(self, *, dex: str | None = None) -> dict:
        return {"universe": [{"name": "ETH", "szDecimals": 4}]}


def test_get_coin_leverage() -> None:
    client = _FakeClient(leverage=7, leverage_type="isolated")
    assert get_coin_leverage(client, "ETH") == CoinLeverage(value=7, type="isolated")


def test_format_order_margin_estimate_opening_order() -> None:
    margin = format_order_margin_estimate(
        {"sz": "0.01", "limitPx": "2000.0", "reduceOnly": False},
        leverage=CoinLeverage(value=5, type="cross"),
    )
    assert margin == "$4.00"


def test_format_order_margin_estimate_reduce_only() -> None:
    margin = format_order_margin_estimate(
        {"sz": "0.01", "limitPx": "2000.0", "reduceOnly": True},
        leverage=CoinLeverage(value=5, type="cross"),
    )
    assert margin == "—"


def test_resolve_order_size_uses_leverage_override() -> None:
    client = _FakeClient(leverage=5)
    resolved = resolve_order_size(client, "ETH", "10", leverage_override=10)
    assert resolved.leverage == 10
    assert resolved.usd_margin == 10.0
    assert resolved.usd_notional == pytest.approx(100.0)


def test_print_open_orders_table_empty() -> None:
    output = StringIO()
    console = Console(file=output, width=120, force_terminal=True)
    print_open_orders_table(console, [], title="Pending orders")
    assert "Pending orders: none." in output.getvalue()


def test_print_open_orders_table_shows_leverage_and_margin() -> None:
    client = MagicMock()
    client.get_active_asset_data.return_value = {
        "leverage": {"type": "cross", "value": 5},
    }
    output = StringIO()
    console = Console(file=output, width=140, force_terminal=True)
    print_open_orders_table(
        console,
        [
            {
                "coin": "ETH",
                "side": "B",
                "orderType": "Limit",
                "sz": "0.0132",
                "limitPx": "1880.0",
                "oid": 123,
                "isTrigger": False,
                "isPositionTpsl": False,
                "reduceOnly": False,
            },
        ],
        title="Pending orders",
        client=client,
    )
    rendered = output.getvalue()
    assert "5x cross" in rendered
    assert "$4.96" in rendered
    assert "fill time" in rendered


def test_print_open_orders_table_includes_trigger_orders() -> None:
    output = StringIO()
    console = Console(file=output, width=120, force_terminal=True)
    print_open_orders_table(
        console,
        [
            {
                "coin": "ETH",
                "side": "A",
                "orderType": "Take Profit Market",
                "sz": "0.01",
                "limitPx": "2200.0",
                "triggerPx": "2200.0",
                "oid": 456,
                "isTrigger": True,
                "isPositionTpsl": True,
                "reduceOnly": True,
            },
        ],
        title="Pending orders",
    )
    rendered = output.getvalue()
    assert "2200.0" in rendered
    assert "(pos)" in rendered
