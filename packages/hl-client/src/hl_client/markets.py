from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedMarket:
    """Normalized Hyperliquid market identifier."""

    coin: str
    dex: str

    @property
    def is_hip3(self) -> bool:
        return bool(self.dex)


def resolve_market(coin: str, dex: str | None = None) -> ResolvedMarket:
    """Resolve a coin symbol to API form, e.g. SPCX + dex=xyz -> xyz:SPCX."""
    raw = coin.strip()
    if not raw:
        raise ValueError("Coin symbol is required.")

    if ":" in raw:
        dex_part, symbol = raw.split(":", 1)
        dex_part = dex_part.strip().lower()
        symbol = symbol.strip().upper()
        if not dex_part or not symbol:
            raise ValueError(f"Invalid market symbol: {coin}")
        if dex is not None and dex.strip().lower() != dex_part:
            raise ValueError(
                f"Coin {coin} already includes dex '{dex_part}', but --dex {dex} was also provided."
            )
        return ResolvedMarket(coin=f"{dex_part}:{symbol}", dex=dex_part)

    symbol = raw.upper()
    if dex:
        return ResolvedMarket(coin=f"{dex.strip().lower()}:{symbol}", dex=dex.strip().lower())
    return ResolvedMarket(coin=symbol, dex="")


def format_market_label(market: ResolvedMarket) -> str:
    return market.coin
