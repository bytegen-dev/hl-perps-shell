from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hl_client.client import HyperliquidClient


def get_info_for_dex(client: HyperliquidClient, dex: str):
    from hyperliquid.info import Info

    if dex not in client._info_by_dex:
        if dex:
            client._info_by_dex[dex] = Info(
                client.settings.api_url,
                skip_ws=client.settings.skip_ws,
                perp_dexs=[dex],
            )
        else:
            client._info_by_dex[dex] = Info(
                client.settings.api_url,
                skip_ws=client.settings.skip_ws,
            )
    return client._info_by_dex[dex]
