import pytest
from hl_client.exceptions import HyperliquidClientError
from hl_client.types import Position
from hl_terminal.sizing import ResolvedOrderSize, resolve_tpsl_size
from hl_terminal.tpsl import format_tpsl_summary, resolve_tpsl_order


class _FakeClient:
    def __init__(
        self,
        *,
        mid: float = 2000.0,
        sz_decimals: int = 4,
        position: Position | None = None,
    ) -> None:
        self._mid = mid
        self._sz_decimals = sz_decimals
        self._position = position

    def get_mid(self, coin: str, *, dex: str | None = None) -> float | None:
        return self._mid

    def get_meta(self, *, dex: str | None = None) -> dict:
        return {"universe": [{"name": "ETH", "szDecimals": self._sz_decimals}]}

    def get_position(self, coin: str, *, dex: str | None = None) -> Position | None:
        return self._position


def _long_position(*, size: float = 0.01, position_value: float = 20.0) -> Position:
    return Position(
        coin="ETH",
        size=size,
        entry_px=1950.0,
        unrealized_pnl=0.5,
        return_on_equity=0.1,
        liquidation_px=1500.0,
        margin_used=4.0,
        position_value=position_value,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )


def test_resolve_tpsl_size_defaults_to_full_position() -> None:
    client = _FakeClient(position=_long_position())
    position, resolved = resolve_tpsl_size(client, "ETH")
    assert position.size == 0.01
    assert resolved.coin_size == 0.01
    assert "full position" in resolved.display


def test_resolve_tpsl_size_partial_percent() -> None:
    client = _FakeClient(position=_long_position())
    _position, resolved = resolve_tpsl_size(client, "ETH", percent=50.0)
    assert resolved.coin_size == 0.005


def test_resolve_tpsl_order_validates_trigger_direction() -> None:
    client = _FakeClient(position=_long_position())
    with pytest.raises(HyperliquidClientError, match="above mark"):
        resolve_tpsl_order(client, "ETH", kind="tp", trigger_px=1900.0)


def test_format_tpsl_summary_market() -> None:
    summary = format_tpsl_summary(
        kind="tp",
        coin="ETH",
        trigger_px=2200.0,
        limit_px=None,
        mode="market",
        resolved=ResolvedOrderSize(
            coin_size=0.01,
            display="full position (0.01 ETH)",
        ),
    )
    assert summary == "TP ETH @ $2,200.00 trigger (market), close full position (0.01 ETH)"


def test_format_tpsl_summary_limit_with_slippage_cap() -> None:
    summary = format_tpsl_summary(
        kind="sl",
        coin="ETH",
        trigger_px=1800.0,
        limit_px=1750.0,
        mode="market",
        resolved=ResolvedOrderSize(
            coin_size=0.01,
            display="full position (0.01 ETH)",
        ),
    )
    assert "max $1,750.00" in summary
    assert summary.startswith("SL ETH @ $1,800.00 trigger")
