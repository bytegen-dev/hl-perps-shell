class HistoricalError(Exception):
    """Base error for historical analysis."""


class TimestampParseError(HistoricalError):
    """Raised when a timestamp string cannot be parsed."""


class InsufficientDataError(HistoricalError):
    """Raised when Hyperliquid returns no candles for the requested window."""
