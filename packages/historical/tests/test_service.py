from hl_historical import HistoricalTracker


def test_live_analyze_signal_smoke() -> None:
    tracker = HistoricalTracker()
    result = tracker.analyze_signal(
        "ETH",
        "2026-08-01T12:00:00Z",
        side="long",
        interval="1h",
        lookback_hours=1,
        forward_hours=12,
        include_funding=False,
    )
    assert result.coin == "ETH"
    assert result.candle_count > 0
    assert result.entry_price > 0


def test_live_hip3_spcx_price() -> None:
    from hl_core.config import HyperliquidSettings

    settings = HyperliquidSettings(network="mainnet", skip_ws=True, _env_file=None)
    tracker = HistoricalTracker(settings=settings)
    price = tracker.get_price_at(
        "xyz:SPCX",
        "2026-08-02T13:00:00Z",
        interval="15m",
    )
    assert price.coin == "xyz:SPCX"
    assert 50 < price.close < 500
