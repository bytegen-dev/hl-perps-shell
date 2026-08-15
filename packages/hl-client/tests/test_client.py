from hl_client import HyperliquidClient
from hl_core.config import HyperliquidSettings


def test_readonly_client_lazy_init() -> None:
    settings = HyperliquidSettings(network="testnet", skip_ws=True, _env_file=None)
    client = HyperliquidClient.readonly(settings)
    assert client._info_by_dex == {}
    assert client._api is None


def test_readonly_client_fetches_mids() -> None:
    settings = HyperliquidSettings(network="testnet", skip_ws=True, _env_file=None)
    client = HyperliquidClient.readonly(settings)
    mids = client.get_all_mids()
    assert isinstance(mids, dict)
    assert len(mids) > 0
    assert "ETH" in mids or "BTC" in mids


def test_get_perp_mids_excludes_spot_symbols() -> None:
    settings = HyperliquidSettings(network="testnet", skip_ws=True, _env_file=None)
    client = HyperliquidClient.readonly(settings)
    perp_mids = client.get_perp_mids()
    assert isinstance(perp_mids, dict)
    assert len(perp_mids) > 0
    assert all(not name.startswith("@") for name in perp_mids)
    assert all(not name.startswith("#") for name in perp_mids)
    assert "BTC" in perp_mids or "ETH" in perp_mids
