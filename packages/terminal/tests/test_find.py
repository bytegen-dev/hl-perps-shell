from io import StringIO
from unittest.mock import MagicMock, patch

from hl_client.markets import PerpMarket
from hl_terminal.find import format_other_network_hint, print_market_search_table
from rich.console import Console


def test_print_market_search_table() -> None:
    output = StringIO()
    console = Console(file=output, width=120, force_terminal=True)
    print_market_search_table(
        console,
        [
            PerpMarket(coin="xyz:SPCX", dex="xyz", sz_decimals=2, max_leverage=20),
            PerpMarket(coin="flx:SPCX", dex="flx", sz_decimals=2, max_leverage=10),
        ],
        mids={"xyz:SPCX": "42.5", "flx:SPCX": "41.0"},
        title='Markets matching "SPCX"',
    )
    rendered = output.getvalue()
    assert "xyz:SPCX" in rendered
    assert "flx:SPCX" in rendered
    assert "42.5" in rendered


def test_format_other_network_hint() -> None:
    with patch("hl_terminal.find.HyperliquidClient") as client_cls:
        client = MagicMock()
        client_cls.readonly.return_value = client
        client.list_perp_markets.return_value = [
            PerpMarket(coin="xyz:SPCX", dex="xyz", sz_decimals=2, max_leverage=20),
        ]
        hint = format_other_network_hint("SPCX", current_network="testnet")
    assert hint == "Found on mainnet: xyz:SPCX"
