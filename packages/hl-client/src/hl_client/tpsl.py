from __future__ import annotations

from typing import Literal

from hl_client.exceptions import HyperliquidClientError

TpslKind = Literal["tp", "sl"]


def validate_tpsl_trigger(
    *,
    kind: TpslKind,
    is_long: bool,
    trigger_px: float,
    mark_px: float,
) -> None:
    if trigger_px <= 0:
        raise HyperliquidClientError("Trigger price must be positive.")
    if mark_px <= 0:
        raise HyperliquidClientError("Mark price unavailable for trigger validation.")

    if is_long:
        if kind == "tp" and trigger_px <= mark_px:
            raise HyperliquidClientError(
                "Long take-profit trigger must be above mark "
                f"({mark_px:,.2f}); got {trigger_px:,.2f}."
            )
        if kind == "sl" and trigger_px >= mark_px:
            raise HyperliquidClientError(
                "Long stop-loss trigger must be below mark "
                f"({mark_px:,.2f}); got {trigger_px:,.2f}."
            )
        return

    if kind == "tp" and trigger_px >= mark_px:
        raise HyperliquidClientError(
            f"Short take-profit trigger must be below mark ({mark_px:,.2f}); got {trigger_px:,.2f}."
        )
    if kind == "sl" and trigger_px <= mark_px:
        raise HyperliquidClientError(
            f"Short stop-loss trigger must be above mark ({mark_px:,.2f}); got {trigger_px:,.2f}."
        )
