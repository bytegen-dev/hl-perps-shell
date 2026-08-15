from hl_core.config import HyperliquidSettings


def test_settings_defaults() -> None:
    settings = HyperliquidSettings(_env_file=None)
    assert settings.network == "testnet"
    assert settings.api_url == "https://api.hyperliquid-testnet.xyz"
    assert settings.skip_ws is True


def test_mainnet_url() -> None:
    settings = HyperliquidSettings(network="mainnet", _env_file=None)
    assert settings.api_url == "https://api.hyperliquid.xyz"
