class HyperliquidClientError(Exception):
    """Base error for hl-client."""


class TradingNotConfiguredError(HyperliquidClientError):
    """Raised when a trading action is requested without signing credentials."""
