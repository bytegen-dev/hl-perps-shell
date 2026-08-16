from __future__ import annotations

from typing import Literal

from hl_client import HyperliquidClient
from hl_client.exceptions import HyperliquidClientError
from hl_client.tpsl import TpslKind, validate_tpsl_trigger
from hl_client.types import Position

from hl_terminal.sizing import ResolvedOrderSize, resolve_tpsl_size

TpslMode = Literal["market", "limit"]


def format_tpsl_summary(
    *,
    kind: TpslKind,
    coin: str,
    trigger_px: float,
    limit_px: float | None,
    mode: TpslMode,
    resolved: ResolvedOrderSize,
) -> str:
    label = "TP" if kind == "tp" else "SL"
    symbol = coin.upper()
    trigger_part = f"{label} {symbol} @ ${trigger_px:,.2f} trigger"
    if mode == "limit":
        exec_px = limit_px if limit_px is not None else trigger_px
        trigger_part = f"{trigger_part} (limit @ ${exec_px:,.2f})"
    elif limit_px is not None and limit_px != trigger_px:
        trigger_part = f"{trigger_part} (market, max ${limit_px:,.2f})"
    else:
        trigger_part = f"{trigger_part} (market)"
    return f"{trigger_part}, close {resolved.display}"


def resolve_tpsl_order(
    client: HyperliquidClient,
    coin: str,
    *,
    kind: TpslKind,
    trigger_px: float,
    raw_size: str | None = None,
    percent: float | None = None,
    usd: bool = False,
    coin_units: bool = False,
) -> tuple[Position, ResolvedOrderSize, float]:
    position, resolved = resolve_tpsl_size(
        client,
        coin,
        raw_size,
        percent=percent,
        usd=usd,
        coin_units=coin_units,
    )
    mark = client.get_mid(coin)
    if mark is None:
        raise HyperliquidClientError(f"No mark price available for {coin.upper()}.")
    validate_tpsl_trigger(
        kind=kind,
        is_long=position.size > 0,
        trigger_px=trigger_px,
        mark_px=mark,
    )
    return position, resolved, mark
