import pytest
from hl_client.markets import PerpMarket, parse_perp_markets, resolve_market, search_perp_markets


def test_resolve_native_market() -> None:
    market = resolve_market("eth")
    assert market.coin == "ETH"
    assert market.dex == ""


def test_resolve_hip3_market_from_prefix() -> None:
    market = resolve_market("xyz:SPCX")
    assert market.coin == "xyz:SPCX"
    assert market.dex == "xyz"


def test_resolve_hip3_market_from_dex_option() -> None:
    market = resolve_market("spcx", dex="xyz")
    assert market.coin == "xyz:SPCX"
    assert market.dex == "xyz"


def test_resolve_rejects_conflicting_dex() -> None:
    with pytest.raises(ValueError):
        resolve_market("xyz:SPCX", dex="flx")


def test_parse_perp_markets() -> None:
    markets = parse_perp_markets(
        dexs=[None, {"name": "xyz"}],
        metas=[
            {"universe": [{"name": "ETH", "szDecimals": 4, "maxLeverage": 50}]},
            {"universe": [{"name": "xyz:SPCX", "szDecimals": 2, "maxLeverage": 20}]},
        ],
    )
    assert len(markets) == 2
    assert markets[0].coin == "ETH"
    assert markets[0].dex == ""
    assert markets[1].coin == "xyz:SPCX"
    assert markets[1].dex == "xyz"


def test_search_perp_markets_matches_substring() -> None:
    markets = [
        PerpMarket(coin="ETH", dex="", sz_decimals=4, max_leverage=50),
        PerpMarket(coin="xyz:SPCX", dex="xyz", sz_decimals=2, max_leverage=20),
        PerpMarket(coin="xyz:SPY", dex="xyz", sz_decimals=2, max_leverage=20),
    ]
    matches = search_perp_markets(markets, "spcx")
    assert [market.coin for market in matches] == ["xyz:SPCX"]


def test_search_perp_markets_requires_query() -> None:
    with pytest.raises(ValueError):
        search_perp_markets([], "  ")
