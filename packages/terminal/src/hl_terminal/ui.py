from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.status import Status

_default_console = Console()


@contextmanager
def loading(message: str, *, console: Console | None = None) -> Iterator[None]:
    """Show a spinner while a slow Hyperliquid operation runs."""
    out = console or _default_console
    with Status(f"[cyan]{message}[/cyan]", spinner="dots", console=out):
        yield
