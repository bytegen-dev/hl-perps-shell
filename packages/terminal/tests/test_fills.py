from datetime import UTC, datetime

from hl_terminal.fills import (
    fill_matches_coin,
    filter_fills,
    format_fill_closed_pnl,
    format_fill_size,
    format_fill_time,
)


def test_fill_matches_coin_by_symbol() -> None:
    fill = {"coin": "ETH"}
    assert fill_matches_coin(fill, "ETH")
    assert fill_matches_coin(fill, "eth")
    assert not fill_matches_coin(fill, "BTC")


def test_fill_matches_coin_with_dex_prefix() -> None:
    fill = {"coin": "xyz:ETH"}
    assert fill_matches_coin(fill, "ETH")
    assert fill_matches_coin(fill, "xyz:ETH")


def test_filter_fills_applies_coin_and_limit() -> None:
    fills = [
        {"coin": "ETH", "time": 3},
        {"coin": "BTC", "time": 2},
        {"coin": "ETH", "time": 1},
    ]
    assert filter_fills(fills, coin="ETH", limit=1) == [{"coin": "ETH", "time": 3}]


def test_format_fill_time_utc() -> None:
    text = format_fill_time(1_681_222_254_710)
    assert text == datetime.fromtimestamp(1_681_222_254_710 / 1000, tz=UTC).strftime(
        "%Y-%m-%d %H:%M"
    )


def test_format_fill_size_shows_usd_and_coin_amount() -> None:
    cell = format_fill_size({"coin": "ETH", "px": "2000", "sz": "0.01"})
    assert "$20.00" in cell
    assert "0.01 ETH" in cell


def test_format_fill_closed_pnl() -> None:
    assert format_fill_closed_pnl({"closedPnl": "0"}) == "-"
    assert format_fill_closed_pnl({"closedPnl": "1.25"}) == "+$1.25"
