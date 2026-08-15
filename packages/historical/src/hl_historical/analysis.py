from __future__ import annotations

from datetime import UTC, datetime

from hl_historical.exceptions import InsufficientDataError
from hl_historical.types import CandleBar, Side, SignalAnalysis


def infer_entry_price(candles: list[CandleBar], signal_ms: int) -> float:
    if not candles:
        raise InsufficientDataError("No candles available to infer entry price.")

    containing = [
        candle
        for candle in candles
        if candle.start_ms <= signal_ms <= candle.end_ms
    ]
    if containing:
        return containing[0].close

    nearest = min(candles, key=lambda candle: abs(candle.start_ms - signal_ms))
    return nearest.close


def analyze_signal_from_candles(
    *,
    coin: str,
    side: Side,
    signal_ms: int,
    entry_price: float,
    interval: str,
    candles: list[CandleBar],
    signal_time: datetime | None = None,
) -> SignalAnalysis:
    if not candles:
        raise InsufficientDataError("No candles returned for the requested window.")

    analysis_candles = [candle for candle in candles if candle.end_ms >= signal_ms]
    if not analysis_candles:
        analysis_candles = candles

    window_high = max(candle.high for candle in analysis_candles)
    window_low = min(candle.low for candle in analysis_candles)
    window_close = analysis_candles[-1].close

    if side == "long":
        mfe_pct = ((window_high - entry_price) / entry_price) * 100
        mae_pct = ((entry_price - window_low) / entry_price) * 100
        final_move_pct = ((window_close - entry_price) / entry_price) * 100
    else:
        mfe_pct = ((entry_price - window_low) / entry_price) * 100
        mae_pct = ((window_high - entry_price) / entry_price) * 100
        final_move_pct = ((entry_price - window_close) / entry_price) * 100

    start_ms = candles[0].start_ms
    end_ms = candles[-1].end_ms
    resolved_signal_time = signal_time or datetime.fromtimestamp(signal_ms / 1000, tz=UTC)

    return SignalAnalysis(
        coin=coin.upper(),
        side=side,
        signal_time=resolved_signal_time,
        signal_ms=signal_ms,
        entry_price=entry_price,
        interval=interval,
        window_start=datetime.fromtimestamp(start_ms / 1000, tz=UTC),
        window_end=datetime.fromtimestamp(end_ms / 1000, tz=UTC),
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        final_move_pct=final_move_pct,
        window_high=window_high,
        window_low=window_low,
        window_close=window_close,
        candle_count=len(analysis_candles),
        funding=(),
    )
