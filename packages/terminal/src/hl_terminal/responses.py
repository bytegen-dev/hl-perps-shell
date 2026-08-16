from __future__ import annotations

import json
from typing import Any

from rich.console import Console


def _raw_payload(result: Any) -> dict[str, Any] | None:
    if hasattr(result, "raw"):
        payload = result.raw  # type: ignore[union-attr]
    elif isinstance(result, dict):
        payload = result
    else:
        return None
    return payload if isinstance(payload, dict) else None


def _order_status_lines(raw: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (severity, message) pairs for order/cancel exchange responses."""
    response = raw.get("response")
    if not isinstance(response, dict):
        return []

    data = response.get("data")
    if not isinstance(data, dict):
        return []

    statuses = data.get("statuses")
    if not isinstance(statuses, list):
        return []

    lines: list[tuple[str, str]] = []
    for status in statuses:
        if isinstance(status, str):
            if status.lower() == "success":
                lines.append(("ok", "Cancel confirmed"))
            else:
                lines.append(("ok", status))
            continue

        if not isinstance(status, dict):
            continue

        if "filled" in status:
            filled = status["filled"]
            if not isinstance(filled, dict):
                continue
            size = filled.get("totalSz", "?")
            avg_px = filled.get("avgPx", "?")
            oid = filled.get("oid", "?")
            lines.append(("ok", f"Filled {size} @ avg {avg_px} (oid {oid})"))
        elif "resting" in status:
            resting = status["resting"]
            if not isinstance(resting, dict):
                continue
            oid = resting.get("oid", "?")
            lines.append(("ok", f"Resting on book (oid {oid})"))
        elif "error" in status:
            lines.append(("error", str(status["error"])))

    return lines


def print_exchange_result(
    console: Console,
    result: Any,
    *,
    headline: str | None = None,
    json_output: bool = False,
) -> None:
    """Print a human-readable summary of a Hyperliquid exchange response."""
    raw = _raw_payload(result)

    if json_output:
        if raw is not None:
            console.print_json(json.dumps(raw, indent=2))
        else:
            console.print_json(json.dumps(result, indent=2, default=str))
        return

    if raw is None:
        console.print(f"[green]✓[/green] {headline or 'Done'}")
        return

    top_status = raw.get("status")
    if top_status != "ok":
        console.print(f"[red]Failed:[/red] {top_status or 'unknown status'}")
        console.print_json(json.dumps(raw, indent=2))
        return

    order_lines = _order_status_lines(raw)
    if order_lines:
        errors = [message for severity, message in order_lines if severity == "error"]
        if errors:
            for message in errors:
                console.print(f"[red]Error:[/red] {message}")
            return

        if headline:
            console.print(f"[green]✓[/green] {headline}")
        for _, message in order_lines:
            console.print(f"  {message}")
        return

    console.print(f"[green]✓[/green] {headline or 'Request accepted'}")
