import pytest
from hl_client.markets import resolve_market


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
