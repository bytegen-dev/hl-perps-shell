from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResolvedMarket:
    """Normalized Hyperliquid market identifier."""

    coin: str
    dex: str

    @property
    def is_hip3(self) -> bool:
        return bool(self.dex)


@dataclass(frozen=True, slots=True)
class PerpMarket:
    coin: str
    dex: str
    sz_decimals: int
    max_leverage: int
    only_isolated: bool = False

    @property
    def dex_label(self) -> str:
        return self.dex or "main"


def _meta_universe(meta: Any) -> list[dict[str, Any]]:
    if isinstance(meta, dict):
        return list(meta["universe"])
    if isinstance(meta, list) and meta:
        first = meta[0]
        if isinstance(first, dict) and "universe" in first:
            return list(first["universe"])
    raise ValueError("Unexpected perp meta shape from Hyperliquid API.")


def parse_perp_markets(
    *,
    dexs: list[Any],
    metas: list[Any],
) -> list[PerpMarket]:
    markets: list[PerpMarket] = []
    for dex_entry, meta in zip(dexs, metas, strict=True):
        dex = ""
        if dex_entry is not None:
            dex = str(dex_entry["name"])
        for asset in _meta_universe(meta):
            markets.append(
                PerpMarket(
                    coin=str(asset["name"]),
                    dex=dex,
                    sz_decimals=int(asset.get("szDecimals", 0)),
                    max_leverage=int(asset.get("maxLeverage", 0)),
                    only_isolated=bool(asset.get("onlyIsolated", False)),
                )
            )
    return markets


def search_perp_markets(markets: list[PerpMarket], query: str) -> list[PerpMarket]:
    needle = query.strip().upper()
    if not needle:
        raise ValueError("Search query is required.")
    return [market for market in markets if needle in market.coin.upper()]


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
