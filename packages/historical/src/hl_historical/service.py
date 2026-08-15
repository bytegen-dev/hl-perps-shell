from __future__ import annotations

from datetime import datetime
from typing import Any

from hl_client import HyperliquidClient
from hl_client.markets import resolve_market
from hl_core.config import HyperliquidSettings, get_settings

from hl_historical.analysis import analyze_signal_from_candles, infer_entry_price
from hl_historical.exceptions import InsufficientDataError
from hl_historical.timeparse import parse_timestamp, to_epoch_ms
from hl_historical.types import (
    CandleBar,
    CandleInterval,
    CandleWindow,
    FundingRecord,
    PriceAtTime,
    Side,
    SignalAnalysis,
)

HOUR_MS = 60 * 60 * 1000


class HistoricalTracker:
    """Shared historical market + signal analysis API.

    Use from the CLI, Telegram bot, or a future HTTP service without duplicating logic.
    """

    def __init__(
        self,
        client: HyperliquidClient | None = None,
        settings: HyperliquidSettings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or HyperliquidClient.readonly(self.settings)

    def get_candles_around(
        self,
        coin: str,
        at: str | int | float | datetime,
        *,
        interval: CandleInterval = "1h",
        lookback_hours: float = 1.0,
        forward_hours: float = 24.0,
        dex: str | None = None,
    ) -> CandleWindow:
        market = resolve_market(coin, dex)
        signal_ms = to_epoch_ms(at)
        start_ms = signal_ms - int(lookback_hours * HOUR_MS)
        end_ms = signal_ms + int(forward_hours * HOUR_MS)
        raw_candles = self.client.get_candles(
            market.coin,
            interval,
            start_ms,
            end_ms,
            dex=market.dex or None,
        )
        candles = tuple(CandleBar.from_api(item) for item in raw_candles)
        if not candles:
            raise InsufficientDataError(
                f"No candles returned for {market.coin} ({interval}) in the requested window."
            )
        return CandleWindow(
            coin=market.coin,
            interval=interval,
            signal_ms=signal_ms,
            start_ms=start_ms,
            end_ms=end_ms,
            candles=candles,
        )

    def get_price_at(
        self,
        coin: str,
        at: str | int | float | datetime,
        *,
        interval: CandleInterval = "15m",
        dex: str | None = None,
    ) -> PriceAtTime:
        window = self.get_candles_around(
            coin,
            at,
            interval=interval,
            lookback_hours=1.0,
            forward_hours=1.0,
            dex=dex,
        )
        signal_ms = window.signal_ms
        containing = [
            candle
            for candle in window.candles
            if candle.start_ms <= signal_ms <= candle.end_ms
        ]
        candle = containing[0] if containing else infer_entry_candle(window.candles, signal_ms)
        return PriceAtTime(
            coin=window.coin,
            time=parse_timestamp(at),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            interval=interval,
        )

    def get_funding_around(
        self,
        coin: str,
        at: str | int | float | datetime,
        *,
        lookback_hours: float = 24.0,
        forward_hours: float = 24.0,
        dex: str | None = None,
    ) -> tuple[FundingRecord, ...]:
        market = resolve_market(coin, dex)
        signal_ms = to_epoch_ms(at)
        start_ms = signal_ms - int(lookback_hours * HOUR_MS)
        end_ms = signal_ms + int(forward_hours * HOUR_MS)
        raw_funding = self.client.get_funding_history(
            market.coin,
            start_ms,
            end_ms,
            dex=market.dex or None,
        )
        return tuple(FundingRecord.from_api(item) for item in raw_funding)

    def analyze_signal(
        self,
        coin: str,
        at: str | int | float | datetime,
        *,
        side: Side,
        entry_price: float | None = None,
        interval: CandleInterval = "1h",
        lookback_hours: float = 1.0,
        forward_hours: float = 24.0,
        include_funding: bool = True,
        dex: str | None = None,
    ) -> SignalAnalysis:
        market = resolve_market(coin, dex)
        window = self.get_candles_around(
            market.coin,
            at,
            interval=interval,
            lookback_hours=lookback_hours,
            forward_hours=forward_hours,
            dex=market.dex or None,
        )
        signal_ms = window.signal_ms
        candles = list(window.candles)
        resolved_entry = entry_price or infer_entry_price(candles, signal_ms)
        funding: tuple[FundingRecord, ...] = ()
        if include_funding:
            funding = self.get_funding_around(
                market.coin,
                at,
                lookback_hours=lookback_hours,
                forward_hours=forward_hours,
                dex=market.dex or None,
            )

        analysis = analyze_signal_from_candles(
            coin=market.coin,
            side=side,
            signal_ms=signal_ms,
            entry_price=resolved_entry,
            interval=interval,
            candles=candles,
            signal_time=parse_timestamp(at),
        )
        return SignalAnalysis(
            coin=analysis.coin,
            side=analysis.side,
            signal_time=analysis.signal_time,
            signal_ms=analysis.signal_ms,
            entry_price=analysis.entry_price,
            interval=analysis.interval,
            window_start=analysis.window_start,
            window_end=analysis.window_end,
            mfe_pct=analysis.mfe_pct,
            mae_pct=analysis.mae_pct,
            final_move_pct=analysis.final_move_pct,
            window_high=analysis.window_high,
            window_low=analysis.window_low,
            window_close=analysis.window_close,
            candle_count=analysis.candle_count,
            funding=funding,
        )

    def analyze_signal_dict(
        self,
        coin: str,
        at: str | int | float | datetime,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = self.analyze_signal(coin, at, **kwargs)  # type: ignore[arg-type]
        payload = result.to_dict()
        if result.funding:
            payload["funding"] = [
                {
                    "time_ms": item.time_ms,
                    "funding_rate": item.funding_rate,
                    "premium": item.premium,
                }
                for item in result.funding
            ]
        return payload


def infer_entry_candle(
    candles: tuple[CandleBar, ...] | list[CandleBar],
    signal_ms: int,
) -> CandleBar:
    return min(candles, key=lambda candle: abs(candle.start_ms - signal_ms))
