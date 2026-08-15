from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Side = Literal["long", "short"]
CandleInterval = Literal[
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M",
]


@dataclass(frozen=True, slots=True)
class PriceAtTime:
    coin: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    interval: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "coin": self.coin,
            "time": self.time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "interval": self.interval,
        }


@dataclass(frozen=True, slots=True)
class CandleBar:
    start_ms: int
    end_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    raw: dict[str, Any]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> CandleBar:
        return cls(
            start_ms=int(payload["t"]),
            end_ms=int(payload["T"]),
            open=float(payload["o"]),
            high=float(payload["h"]),
            low=float(payload["l"]),
            close=float(payload["c"]),
            volume=float(payload["v"]),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class FundingRecord:
    time_ms: int
    coin: str
    funding_rate: float
    premium: float
    raw: dict[str, Any]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> FundingRecord:
        return cls(
            time_ms=int(payload["time"]),
            coin=str(payload["coin"]),
            funding_rate=float(payload["fundingRate"]),
            premium=float(payload["premium"]),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class CandleWindow:
    coin: str
    interval: str
    signal_ms: int
    start_ms: int
    end_ms: int
    candles: tuple[CandleBar, ...]


@dataclass(frozen=True, slots=True)
class SignalAnalysis:
    coin: str
    side: Side
    signal_time: datetime
    signal_ms: int
    entry_price: float
    interval: str
    window_start: datetime
    window_end: datetime
    mfe_pct: float
    mae_pct: float
    final_move_pct: float
    window_high: float
    window_low: float
    window_close: float
    candle_count: int
    funding: tuple[FundingRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coin": self.coin,
            "side": self.side,
            "signal_time": self.signal_time.isoformat(),
            "signal_ms": self.signal_ms,
            "entry_price": self.entry_price,
            "interval": self.interval,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "mfe_pct": round(self.mfe_pct, 4),
            "mae_pct": round(self.mae_pct, 4),
            "final_move_pct": round(self.final_move_pct, 4),
            "window_high": self.window_high,
            "window_low": self.window_low,
            "window_close": self.window_close,
            "candle_count": self.candle_count,
            "funding_count": len(self.funding),
        }
