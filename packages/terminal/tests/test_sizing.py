import math

import pytest
from hl_client.exceptions import HyperliquidClientError
from hl_terminal.sizing import (
    estimate_close_proceeds,
    format_margin_cell,
    format_pnl,
    format_size_cell,
    format_total_upnl,
    format_usd,
    parse_close_size_spec,
    parse_size_spec,
    resolve_close_size,
    resolve_mark_price,
    resolve_order_size,
    round_size_down,
    total_positions_margin,
    total_positions_notional,
    total_positions_upnl,
)


class _FakeClient:
    def __init__(
        self,
        *,
        mid: float = 2000.0,
        sz_decimals: int = 4,
        leverage: int = 5,
        position: object | None = None,
    ) -> None:
        self._mid = mid
        self._sz_decimals = sz_decimals
        self._leverage = leverage
        self._position = position

    def get_mid(self, coin: str, *, dex: str | None = None) -> float | None:
        return self._mid

    def get_meta(self, *, dex: str | None = None) -> dict:
        return {"universe": [{"name": "ETH", "szDecimals": self._sz_decimals}]}

    def get_active_asset_data(self, coin: str, *, dex: str | None = None) -> dict:
        return {"leverage": {"type": "cross", "value": self._leverage}}

    def get_position(self, coin: str, *, dex: str | None = None) -> object | None:
        return self._position


def test_parse_size_spec_defaults_to_usd_margin() -> None:
    assert parse_size_spec("30").usd_margin == 30.0


def test_parse_size_spec_notional_flag() -> None:
    assert parse_size_spec("30", notional=True).usd_notional == 30.0


def test_parse_size_spec_coin_units_flag() -> None:
    assert parse_size_spec("0.01", coin_units=True).coin == 0.01


def test_parse_size_spec_coin_suffix() -> None:
    assert parse_size_spec("0.01eth", coin="ETH").coin == 0.01


def test_parse_size_spec_usd_prefix() -> None:
    assert parse_size_spec("$30").usd_margin == 30.0


def test_parse_size_spec_usd_suffix() -> None:
    assert parse_size_spec("30usd").usd_margin == 30.0
    assert parse_size_spec("30 USDC").usd_margin == 30.0


def test_parse_close_size_spec_percent() -> None:
    assert parse_close_size_spec("50%").percent == 50.0
    assert parse_close_size_spec("12.5%").percent == 12.5


def test_parse_close_size_spec_usd_notional() -> None:
    assert parse_close_size_spec("15").usd_notional == 15.0
    assert parse_close_size_spec("0.005", coin_units=True).coin == 0.005


def test_parse_close_size_spec_rejects_invalid_percent() -> None:
    with pytest.raises(ValueError, match="Percent must be"):
        parse_close_size_spec("150%")


def _sample_eth_position() -> object:
    from hl_client.types import Position

    return Position(
        coin="ETH",
        size=0.0159,
        entry_px=1882.7,
        unrealized_pnl=0.0,
        return_on_equity=0.0,
        liquidation_px=None,
        margin_used=5.99,
        position_value=29.93,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )


def test_resolve_close_size_from_percent() -> None:
    resolved = resolve_close_size(
        _FakeClient(mid=1882.7, position=_sample_eth_position()),
        "ETH",
        "50%",
    )
    assert resolved.coin_size == round_size_down(0.0159 * 0.5, 4)
    assert resolved.display == "50%. $2.98 (0.0079 ETH)"


def test_resolve_close_size_from_percent_flag() -> None:
    resolved = resolve_close_size(
        _FakeClient(mid=1882.7, position=_sample_eth_position()),
        "ETH",
        percent=50,
    )
    assert resolved.coin_size == round_size_down(0.0159 * 0.5, 4)
    assert resolved.display == "50%. $2.98 (0.0079 ETH)"


def test_resolve_close_size_from_usd_notional() -> None:
    resolved = resolve_close_size(
        _FakeClient(mid=1882.7, position=_sample_eth_position()),
        "ETH",
        "15",
    )
    assert resolved.coin_size == 0.0079
    assert resolved.usd_notional == pytest.approx(14.87, abs=0.01)
    assert resolved.display == "$2.98 (0.0079 ETH)"


def test_estimate_close_proceeds_includes_margin_and_upnl() -> None:
    from hl_client.types import Position

    pos = Position(
        coin="ETH",
        size=0.0159,
        entry_px=1882.7,
        unrealized_pnl=0.14,
        return_on_equity=0.02,
        liquidation_px=None,
        margin_used=6.01,
        position_value=30.0,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )
    proceeds = estimate_close_proceeds(pos, round_size_down(0.0159 * 0.2, 4))
    assert proceeds == pytest.approx(1.20, abs=0.01)


def test_resolve_close_size_rejects_partial_below_min_notional() -> None:
    with pytest.raises(HyperliquidClientError, match="Close at least 34%"):
        resolve_close_size(
            _FakeClient(mid=1882.7, position=_sample_eth_position()),
            "ETH",
            "20%",
        )


def test_resolve_close_size_rejects_excess_notional() -> None:
    with pytest.raises(HyperliquidClientError, match="exceeds position"):
        resolve_close_size(
            _FakeClient(mid=1882.7, position=_sample_eth_position()),
            "ETH",
            "50",
        )


def test_resolve_close_size_requires_open_position() -> None:
    with pytest.raises(HyperliquidClientError, match="No open position"):
        resolve_close_size(_FakeClient(), "ETH", "50%")


def test_round_size_down_respects_sz_decimals() -> None:
    assert round_size_down(0.015957, 4) == 0.0159


def test_resolve_order_size_from_margin() -> None:
    resolved = resolve_order_size(_FakeClient(mid=2000.0, leverage=5), "ETH", "30")
    assert resolved.coin_size == 0.075
    assert resolved.usd_margin == 30.0
    assert resolved.usd_notional == 150.0
    assert resolved.leverage == 5
    assert "$30.00 margin" in resolved.display


def test_resolve_order_size_from_notional() -> None:
    resolved = resolve_order_size(
        _FakeClient(mid=2000.0, leverage=5),
        "ETH",
        "30",
        notional=True,
    )
    assert resolved.coin_size == 0.015
    assert resolved.usd_notional == 30.0
    assert "$30.00 size" in resolved.display


def test_resolve_order_size_rejects_below_min_notional() -> None:
    with pytest.raises(HyperliquidClientError, match="minimum"):
        resolve_order_size(_FakeClient(mid=2000.0, leverage=5), "ETH", "1")


def test_resolve_order_size_limit_uses_limit_price() -> None:
    resolved = resolve_order_size(
        _FakeClient(mid=9999.0, leverage=5),
        "ETH",
        "30",
        notional=True,
        price=1500.0,
    )
    assert math.isclose(resolved.coin_size, round_size_down(30 / 1500, 4))
    assert resolved.reference_price == 1500.0


def test_format_usd_signed() -> None:
    assert format_usd(-0.01, signed=True) == "$-0.01"


def test_format_pnl_zero() -> None:
    assert format_pnl(0.0) == "+$0.00"
    assert format_pnl(0.0, return_on_equity=0.0) == "+$0.00 (+0.0000%)"


def test_format_pnl_small_value_uses_four_decimals() -> None:
    assert format_pnl(-0.0008) == "-$0.0008"


def test_format_pnl_large_value_uses_two_decimals() -> None:
    assert format_pnl(12.345) == "+$12.35"


def test_format_pnl_includes_roe_percentage() -> None:
    assert format_pnl(-0.0032, return_on_equity=-0.000534) == "-$0.0032 (-0.0534%)"


def test_format_size_cell_shows_usd_and_coin_amount() -> None:
    from hl_client.types import Position

    pos = Position(
        coin="ETH",
        size=0.0159,
        entry_px=1882.7,
        unrealized_pnl=0.0,
        return_on_equity=0.0,
        liquidation_px=None,
        margin_used=5.99,
        position_value=29.93,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )
    cell = format_size_cell(pos)
    assert "$29.93" in cell
    assert "0.0159 ETH" in cell


def test_format_margin_cell_shows_usd_and_coin_equivalent() -> None:
    from hl_client.types import Position

    pos = Position(
        coin="ETH",
        size=0.0159,
        entry_px=1882.7,
        unrealized_pnl=0.0,
        return_on_equity=0.0,
        liquidation_px=None,
        margin_used=5.99,
        position_value=29.93,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )
    cell = format_margin_cell(pos, 1882.7)
    assert "$5.99" in cell
    assert "ETH" in cell


def test_total_positions_notional() -> None:
    from hl_client.types import Position

    positions = [
        Position(
            coin="ETH",
            size=0.01,
            entry_px=1800.0,
            unrealized_pnl=1.0,
            return_on_equity=0.1,
            liquidation_px=None,
            margin_used=5.0,
            position_value=18.0,
            leverage_type="isolated",
            leverage_value=5,
            raw={},
        ),
        Position(
            coin="BTC",
            size=-0.001,
            entry_px=60000.0,
            unrealized_pnl=-0.5,
            return_on_equity=-0.05,
            liquidation_px=None,
            margin_used=10.0,
            position_value=60.0,
            leverage_type="isolated",
            leverage_value=3,
            raw={},
        ),
    ]
    assert total_positions_notional(positions) == 78.0
    assert total_positions_notional([]) == 0.0


def test_total_positions_margin() -> None:
    from hl_client.types import Position

    positions = [
        Position(
            coin="ETH",
            size=0.01,
            entry_px=1800.0,
            unrealized_pnl=1.0,
            return_on_equity=0.1,
            liquidation_px=None,
            margin_used=5.0,
            position_value=18.0,
            leverage_type="isolated",
            leverage_value=5,
            raw={},
        ),
        Position(
            coin="BTC",
            size=-0.001,
            entry_px=60000.0,
            unrealized_pnl=-0.5,
            return_on_equity=-0.05,
            liquidation_px=None,
            margin_used=10.0,
            position_value=60.0,
            leverage_type="isolated",
            leverage_value=3,
            raw={},
        ),
    ]
    assert total_positions_margin(positions) == 15.0
    assert total_positions_margin([]) == 0.0


def test_total_positions_upnl() -> None:
    from hl_client.types import Position

    positions = [
        Position(
            coin="ETH",
            size=0.01,
            entry_px=1800.0,
            unrealized_pnl=1.0,
            return_on_equity=0.1,
            liquidation_px=None,
            margin_used=5.0,
            position_value=18.0,
            leverage_type="isolated",
            leverage_value=5,
            raw={},
        ),
        Position(
            coin="BTC",
            size=-0.001,
            entry_px=60000.0,
            unrealized_pnl=-0.5,
            return_on_equity=-0.05,
            liquidation_px=None,
            margin_used=10.0,
            position_value=60.0,
            leverage_type="isolated",
            leverage_value=3,
            raw={},
        ),
    ]
    assert total_positions_upnl(positions) == 0.5
    assert total_positions_upnl([]) == 0.0
    assert format_total_upnl(positions) == "+$0.50 (+3.33%)"
    assert format_total_upnl([]) == "+$0.00"


def test_resolve_mark_price_from_mids() -> None:
    from hl_client.types import Position

    pos = Position(
        coin="ETH",
        size=0.01,
        entry_px=1800.0,
        unrealized_pnl=1.0,
        return_on_equity=0.1,
        liquidation_px=None,
        margin_used=5.0,
        position_value=18.0,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )
    assert resolve_mark_price(pos, {"ETH": 1882.7}) == 1882.7


def test_resolve_mark_price_falls_back_to_position_value() -> None:
    from hl_client.types import Position

    pos = Position(
        coin="ETH",
        size=0.01,
        entry_px=1800.0,
        unrealized_pnl=1.0,
        return_on_equity=0.1,
        liquidation_px=None,
        margin_used=5.0,
        position_value=18.827,
        leverage_type="cross",
        leverage_value=5,
        raw={},
    )
    assert resolve_mark_price(pos, {}) == 1882.7
