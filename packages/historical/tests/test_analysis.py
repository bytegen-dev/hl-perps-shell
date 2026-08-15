from datetime import UTC, datetime

import pytest
from hl_historical.analysis import analyze_signal_from_candles, infer_entry_price
from hl_historical.timeparse import parse_timestamp, to_epoch_ms
from hl_historical.types import CandleBar


def _candle(
    *,
    start_ms: int,
    end_ms: int,
    open_px: float,
    high: float,
    low: float,
    close: float,
) -> CandleBar:
    return CandleBar(
        start_ms=start_ms,
        end_ms=end_ms,
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        raw={},
    )


def test_parse_timestamp_iso_and_unix() -> None:
    iso = parse_timestamp("2026-08-13T12:00:00Z")
    assert iso == datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    assert to_epoch_ms("2026-08-13T12:00:00Z") == int(iso.timestamp() * 1000)
    assert to_epoch_ms(1_700_000_000) == 1_700_000_000_000


def test_long_signal_mfe_mae() -> None:
    signal_ms = 1_700_000_000_000
    candles = [
        _candle(
            start_ms=signal_ms - 3_600_000,
            end_ms=signal_ms,
            open_px=100,
            high=101,
            low=99,
            close=100,
        ),
        _candle(
            start_ms=signal_ms,
            end_ms=signal_ms + 3_600_000,
            open_px=100,
            high=110,
            low=95,
            close=105,
        ),
    ]
    result = analyze_signal_from_candles(
        coin="ETH",
        side="long",
        signal_ms=signal_ms,
        entry_price=100,
        interval="1h",
        candles=candles,
        signal_time=datetime.fromtimestamp(signal_ms / 1000, tz=UTC),
    )
    assert result.mfe_pct == pytest.approx(10.0)
    assert result.mae_pct == pytest.approx(5.0)
    assert result.final_move_pct == pytest.approx(5.0)


def test_infer_entry_price_uses_signal_candle_close() -> None:
    signal_ms = 1_700_000_000_000
    candles = [
        _candle(
            start_ms=signal_ms,
            end_ms=signal_ms + 3_600_000,
            open_px=100,
            high=101,
            low=99,
            close=123.45,
        )
    ]
    assert infer_entry_price(candles, signal_ms) == pytest.approx(123.45)
