from __future__ import annotations

from hl_client import HyperliquidClient
from hl_client.markets import PerpMarket, search_perp_markets
from hl_core.config import HyperliquidSettings, Network
from rich.console import Console
from rich.table import Table


def fetch_mids_for_markets(
    client: HyperliquidClient,
    markets: list[PerpMarket],
) -> dict[str, str]:
    dexes = {market.dex for market in markets}
    mids: dict[str, str] = {}
    for dex in dexes:
        mids.update(client.get_all_mids(dex=dex or None))
    return mids


def print_market_search_table(
    console: Console,
    markets: list[PerpMarket],
    *,
    mids: dict[str, str],
    title: str,
) -> None:
    table = Table(title=title)
    table.add_column("Coin", style="cyan")
    table.add_column("Dex")
    table.add_column("Mid", justify="right")
    table.add_column("Max lev", justify="right")
    table.add_column("Size dec", justify="right")

    for market in sorted(markets, key=lambda item: item.coin):
        mid = mids.get(market.coin, "—")
        isolated = " iso" if market.only_isolated else ""
        table.add_row(
            market.coin,
            market.dex_label,
            mid,
            f"{market.max_leverage}x{isolated}",
            str(market.sz_decimals),
        )

    console.print(table)


def find_perp_markets(
    client: HyperliquidClient,
    query: str,
    *,
    dex: str | None = None,
) -> list[PerpMarket]:
    markets = client.list_perp_markets()
    if dex is not None:
        dex_name = dex.strip().lower()
        markets = [market for market in markets if market.dex == dex_name]
    return search_perp_markets(markets, query)


def format_other_network_hint(
    query: str,
    *,
    current_network: Network,
    dex: str | None = None,
    limit: int = 5,
) -> str | None:
    other_network: Network = "mainnet" if current_network == "testnet" else "testnet"
    client = HyperliquidClient.readonly(
        HyperliquidSettings(network=other_network, skip_ws=True, _env_file=None)
    )
    matches = find_perp_markets(client, query, dex=dex)
    if not matches:
        return None

    shown = ", ".join(market.coin for market in sorted(matches, key=lambda item: item.coin)[:limit])
    if len(matches) > limit:
        shown = f"{shown} (+{len(matches) - limit} more)"
    return f"Found on {other_network}: {shown}"
