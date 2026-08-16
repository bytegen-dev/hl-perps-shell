from __future__ import annotations

import math
import re
from dataclasses import dataclass

from hl_client import HyperliquidClient
from hl_client.exceptions import HyperliquidClientError
from hl_client.markets import resolve_market
from hl_client.types import Position
from rich.console import Console
from rich.table import Table

MIN_NOTIONAL_USD = 10.0
_COIN_SIZE_SUFFIX = re.compile(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z][\w:]*)$")
_PERCENT_SUFFIX = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")


@dataclass(frozen=True, slots=True)
class SizeSpec:
    coin: float | None = None
    usd_margin: float | None = None
    usd_notional: float | None = None


@dataclass(frozen=True, slots=True)
class CloseSizeSpec:
    coin: float | None = None
    usd_notional: float | None = None
    percent: float | None = None


@dataclass(frozen=True, slots=True)
class ResolvedOrderSize:
    coin_size: float
    display: str
    usd_notional: float | None = None
    usd_margin: float | None = None
    reference_price: float | None = None
    leverage: int | None = None
    leverage_type: str | None = None


@dataclass(frozen=True, slots=True)
class CoinLeverage:
    value: int
    type: str

    @property
    def label(self) -> str:
        return f"{self.value}x {self.type}"


def get_coin_leverage(
    client: HyperliquidClient,
    coin: str,
    *,
    dex: str | None = None,
) -> CoinLeverage:
    asset_data = client.get_active_asset_data(coin, dex=dex)
    leverage = asset_data["leverage"]
    return CoinLeverage(value=int(leverage["value"]), type=str(leverage["type"]))


def format_order_margin_estimate(
    order: dict[str, object],
    *,
    leverage: CoinLeverage | None,
) -> str:
    if order.get("reduceOnly") or leverage is None or leverage.value <= 0:
        return "—"
    try:
        size = float(str(order["sz"]))
        price = float(str(order["limitPx"]))
    except (KeyError, TypeError, ValueError):
        return "—"
    if size <= 0 or price <= 0:
        return "—"
    return format_usd(size * price / leverage.value)


def parse_size_spec(
    raw: str,
    *,
    coin: str | None = None,
    usd: bool = False,
    coin_units: bool = False,
    notional: bool = False,
) -> SizeSpec:
    text = raw.strip()
    if not text:
        raise ValueError("Size is required.")

    if coin_units:
        return SizeSpec(coin=_parse_positive_amount(text))

    if usd or text.startswith("$"):
        amount_text = text[1:].strip() if text.startswith("$") else text
        lowered = amount_text.lower()
        for suffix in ("usdc", "usd"):
            if lowered.endswith(suffix):
                amount_text = amount_text[: -len(suffix)].strip()
                break
        amount = _parse_positive_amount(amount_text)
        if notional:
            return SizeSpec(usd_notional=amount)
        return SizeSpec(usd_margin=amount)

    lowered = text.lower()
    for suffix in ("usdc", "usd"):
        if lowered.endswith(suffix):
            num_text = text[: -len(suffix)].strip()
            amount = _parse_positive_amount(num_text)
            if notional:
                return SizeSpec(usd_notional=amount)
            return SizeSpec(usd_margin=amount)

    if coin:
        match = _COIN_SIZE_SUFFIX.match(text)
        if match and match.group(2).lower() == coin.strip().lower():
            return SizeSpec(coin=_parse_positive_amount(match.group(1)))

    amount = _parse_positive_amount(text)
    if notional:
        return SizeSpec(usd_notional=amount)
    return SizeSpec(usd_margin=amount)


def _parse_positive_amount(text: str) -> float:
    try:
        amount = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid size: {text!r}") from exc
    if amount <= 0:
        raise ValueError("Size must be positive.")
    return amount


def parse_close_size_spec(
    raw: str,
    *,
    coin: str | None = None,
    usd: bool = False,
    coin_units: bool = False,
) -> CloseSizeSpec:
    text = raw.strip()
    if not text:
        raise ValueError("Size is required.")

    percent_match = _PERCENT_SUFFIX.match(text)
    if percent_match is not None:
        return CloseSizeSpec(percent=_parse_percent_amount(percent_match.group(1)))

    spec = parse_size_spec(
        raw,
        coin=coin,
        usd=usd,
        coin_units=coin_units,
        notional=True,
    )
    if spec.coin is not None:
        return CloseSizeSpec(coin=spec.coin)
    assert spec.usd_notional is not None
    return CloseSizeSpec(usd_notional=spec.usd_notional)


def _parse_percent_amount(text: str) -> float:
    try:
        percent = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid percent: {text!r}") from exc
    if percent <= 0 or percent > 100:
        raise ValueError("Percent must be between 0 and 100.")
    return percent


def _sz_decimals(client: HyperliquidClient, coin: str, *, dex: str | None = None) -> int:
    market = resolve_market(coin, dex)
    meta = client.get_meta(dex=market.dex or None)
    for asset in meta["universe"]:
        if asset["name"] == market.coin:
            return int(asset["szDecimals"])
    raise HyperliquidClientError(f"Could not find size decimals for {market.coin}.")


def round_size_down(size: float, sz_decimals: int) -> float:
    factor = 10**sz_decimals
    return math.floor(size * factor + 1e-12) / factor


def format_usd(amount: float, *, signed: bool = False) -> str:
    if signed:
        return f"${amount:+,.2f}"
    return f"${amount:,.2f}"


def format_signed_usd(amount: float) -> str:
    """Format USD with sign before the dollar, e.g. +$12.34 or -$0.0008."""
    if abs(amount) < 1e-9:
        return "+$0.00"
    if abs(amount) < 0.01:
        decimals = 4
    else:
        decimals = 2
    if amount >= 0:
        return f"+${amount:,.{decimals}f}"
    return f"-${abs(amount):,.{decimals}f}"


def format_roe(return_on_equity: float) -> str:
    pct = return_on_equity * 100
    if abs(pct) < 0.1:
        return f"{pct:+.4f}%"
    return f"{pct:+.2f}%"


def format_pnl(amount: float, *, return_on_equity: float | None = None) -> str:
    """Format uPnL with optional ROE percentage on margin."""
    usd_part = format_signed_usd(amount)
    if return_on_equity is None:
        return usd_part
    return f"{usd_part} ({format_roe(return_on_equity)})"


def position_coin_symbol(coin: str) -> str:
    return coin.split(":")[-1].upper()


def format_size_cell(pos: Position) -> str:
    coin_symbol = position_coin_symbol(pos.coin)
    coin_amount = f"{abs(pos.size):g} {coin_symbol}"
    return f"{format_usd(abs(pos.position_value))}\n[dim]{coin_amount}[/dim]"


def format_margin_cell(pos: Position, mark: float | None) -> str:
    usd_margin = format_usd(pos.margin_used)
    if mark is None or mark <= 0:
        return usd_margin
    coin_symbol = position_coin_symbol(pos.coin)
    coin_amount = f"{pos.margin_used / mark:g} {coin_symbol}"
    return f"{usd_margin}\n[dim]{coin_amount}[/dim]"


def format_order_size_display(
    *,
    coin: str,
    coin_size: float,
    reference_price: float | None,
    usd_margin: float | None = None,
    usd_notional: float | None = None,
    leverage: int | None = None,
) -> str:
    symbol = coin.upper()
    notional = coin_size * reference_price if reference_price is not None else usd_notional

    if usd_margin is not None and notional is not None and leverage is not None:
        return (
            f"{format_usd(usd_margin)} margin → {format_usd(notional)} size "
            f"(~{coin_size:g} {symbol} @ {format_usd(reference_price)}, {leverage}x)"
        )
    if usd_notional is not None and notional is not None:
        return (
            f"{format_usd(notional)} size "
            f"(~{coin_size:g} {symbol} @ {format_usd(reference_price)})"
        )
    if notional is not None:
        return (
            f"{format_usd(notional)} size "
            f"(~{coin_size:g} {symbol} @ {format_usd(reference_price)})"
        )
    return f"{coin_size:g} {symbol}"


def _resolve_reference_price(
    client: HyperliquidClient,
    coin: str,
    *,
    price: float | None,
    dex: str | None,
    symbol: str,
) -> float:
    if price is not None:
        return price
    mid = client.get_mid(coin, dex=dex)
    if mid is None:
        raise HyperliquidClientError(f"No mid price available for {symbol}.")
    return mid


def _resolve_usd_notional_size(
    client: HyperliquidClient,
    coin: str,
    *,
    usd_notional: float,
    reference_price: float,
    dex: str | None,
    symbol: str,
    enforce_min_notional: bool = True,
) -> tuple[float, float]:
    sz_decimals = _sz_decimals(client, coin, dex=dex)
    coin_size = round_size_down(usd_notional / reference_price, sz_decimals)
    if coin_size <= 0:
        min_increment = 10**-sz_decimals
        raise HyperliquidClientError(
            f"{format_usd(usd_notional)} is too small for {symbol} at "
            f"{format_usd(reference_price)} (min increment {min_increment:g} {symbol})."
        )
    actual_notional = coin_size * reference_price
    if enforce_min_notional and actual_notional < MIN_NOTIONAL_USD:
        raise HyperliquidClientError(
            f"Order notional {format_usd(actual_notional)} is below Hyperliquid's "
            f"~{format_usd(MIN_NOTIONAL_USD)} minimum."
        )
    return coin_size, actual_notional


def resolve_order_size(
    client: HyperliquidClient,
    coin: str,
    raw_size: str,
    *,
    price: float | None = None,
    dex: str | None = None,
    usd: bool = False,
    coin_units: bool = False,
    notional: bool = False,
    leverage_override: int | None = None,
) -> ResolvedOrderSize:
    spec = parse_size_spec(
        raw_size,
        coin=coin,
        usd=usd,
        coin_units=coin_units,
        notional=notional,
    )
    symbol = coin.upper()

    if spec.coin is not None:
        reference_price = _resolve_reference_price(
            client, coin, price=price, dex=dex, symbol=symbol
        )
        coin_notional = spec.coin * reference_price
        if coin_notional < MIN_NOTIONAL_USD:
            raise HyperliquidClientError(
                f"Order notional {format_usd(coin_notional)} is below Hyperliquid's "
                f"~{format_usd(MIN_NOTIONAL_USD)} minimum."
            )
        return ResolvedOrderSize(
            coin_size=spec.coin,
            reference_price=reference_price,
            usd_notional=coin_notional,
            display=format_order_size_display(
                coin=coin,
                coin_size=spec.coin,
                reference_price=reference_price,
                usd_notional=coin_notional,
            ),
        )

    reference_price = _resolve_reference_price(
        client, coin, price=price, dex=dex, symbol=symbol
    )

    if spec.usd_notional is not None:
        coin_size, actual_notional = _resolve_usd_notional_size(
            client,
            coin,
            usd_notional=spec.usd_notional,
            reference_price=reference_price,
            dex=dex,
            symbol=symbol,
        )
        return ResolvedOrderSize(
            coin_size=coin_size,
            usd_notional=actual_notional,
            reference_price=reference_price,
            display=format_order_size_display(
                coin=coin,
                coin_size=coin_size,
                reference_price=reference_price,
                usd_notional=actual_notional,
            ),
        )

    assert spec.usd_margin is not None
    coin_leverage = get_coin_leverage(client, coin, dex=dex)
    leverage = leverage_override if leverage_override is not None else coin_leverage.value
    target_notional = spec.usd_margin * leverage
    coin_size, actual_notional = _resolve_usd_notional_size(
        client,
        coin,
        usd_notional=target_notional,
        reference_price=reference_price,
        dex=dex,
        symbol=symbol,
    )

    return ResolvedOrderSize(
        coin_size=coin_size,
        usd_margin=spec.usd_margin,
        usd_notional=actual_notional,
        reference_price=reference_price,
        leverage=leverage,
        leverage_type=coin_leverage.type,
        display=format_order_size_display(
            coin=coin,
            coin_size=coin_size,
            reference_price=reference_price,
            usd_margin=spec.usd_margin,
            usd_notional=actual_notional,
            leverage=leverage,
        ),
    )


def estimate_close_proceeds(position: Position, coin_size: float) -> float:
    """Estimate USDC returned to wallet from margin release + realized PnL."""
    total_coin_size = abs(position.size)
    if total_coin_size <= 1e-12:
        return 0.0
    fraction = min(coin_size / total_coin_size, 1.0)
    return fraction * (position.margin_used + position.unrealized_pnl)


def format_wallet_proceeds(amount: float) -> str:
    if amount < 0:
        return format_signed_usd(amount)
    return format_usd(amount)


def format_close_proceeds_display(
    *,
    position: Position,
    coin_size: float,
    percent: float | None = None,
) -> str:
    proceeds = estimate_close_proceeds(position, coin_size)
    symbol = position_coin_symbol(position.coin)
    wallet_part = format_wallet_proceeds(proceeds)
    size_part = f"({coin_size:g} {symbol})"
    if percent is not None:
        return f"{percent:g}%. {wallet_part} {size_part}"
    return f"{wallet_part} {size_part}"


def _require_open_position(
    client: HyperliquidClient,
    coin: str,
    *,
    dex: str | None = None,
) -> Position:
    position = client.get_position(coin, dex=dex)
    if position is None:
        raise HyperliquidClientError(f"No open position for {coin.upper()}.")
    return position


def _cap_close_coin_size(
    *,
    coin_size: float,
    position: Position,
    client: HyperliquidClient,
    coin: str,
    dex: str | None,
    symbol: str,
) -> float:
    max_size = abs(position.size)
    if coin_size > max_size + 1e-12:
        raise HyperliquidClientError(
            f"Close size ~{coin_size:g} {symbol} exceeds position "
            f"size {max_size:g} {symbol} ({format_usd(abs(position.position_value))})."
        )
    sz_decimals = _sz_decimals(client, coin, dex=dex)
    return round_size_down(min(coin_size, max_size), sz_decimals)


def _validate_partial_close_notional(
    *,
    actual_notional: float,
    coin_size: float,
    max_coin_size: float,
    max_notional: float,
    symbol: str,
) -> None:
    if coin_size >= max_coin_size - 1e-12:
        return
    if actual_notional >= MIN_NOTIONAL_USD - 0.01:
        return
    if max_notional < MIN_NOTIONAL_USD:
        raise HyperliquidClientError(
            f"Position notional {format_usd(max_notional)} is below Hyperliquid's "
            f"{format_usd(MIN_NOTIONAL_USD)} minimum — partial closes aren't supported. "
            f"Run `hl close {symbol}` to exit fully."
        )
    min_percent = math.ceil(MIN_NOTIONAL_USD / max_notional * 100)
    raise HyperliquidClientError(
        f"Partial close notional {format_usd(actual_notional)} is below Hyperliquid's "
        f"{format_usd(MIN_NOTIONAL_USD)} minimum order size. "
        f"Close at least {min_percent}% of the position, "
        f"or run `hl close {symbol}` to exit fully."
    )


def _build_resolved_close_size(
    *,
    position: Position,
    coin_size: float,
    actual_notional: float,
    reference_price: float,
    max_coin_size: float,
    symbol: str,
    percent: float | None = None,
) -> ResolvedOrderSize:
    _validate_partial_close_notional(
        actual_notional=actual_notional,
        coin_size=coin_size,
        max_coin_size=max_coin_size,
        max_notional=abs(position.position_value),
        symbol=symbol,
    )
    return ResolvedOrderSize(
        coin_size=coin_size,
        usd_notional=actual_notional,
        reference_price=reference_price,
        display=format_close_proceeds_display(
            position=position,
            coin_size=coin_size,
            percent=percent,
        ),
    )


def resolve_tpsl_size(
    client: HyperliquidClient,
    coin: str,
    raw_size: str | None = None,
    *,
    percent: float | None = None,
    dex: str | None = None,
    usd: bool = False,
    coin_units: bool = False,
) -> tuple[Position, ResolvedOrderSize]:
    position = _require_open_position(client, coin, dex=dex)
    symbol = position_coin_symbol(position.coin)
    max_coin_size = abs(position.size)

    if raw_size is None and percent is None:
        reference_price = _resolve_reference_price(
            client, coin, price=None, dex=dex, symbol=symbol
        )
        return position, ResolvedOrderSize(
            coin_size=max_coin_size,
            usd_notional=max_coin_size * reference_price,
            reference_price=reference_price,
            display=f"full position ({max_coin_size:g} {symbol})",
        )

    resolved = resolve_close_size(
        client,
        coin,
        raw_size,
        percent=percent,
        dex=dex,
        usd=usd,
        coin_units=coin_units,
    )
    return position, resolved


def resolve_close_size(
    client: HyperliquidClient,
    coin: str,
    raw_size: str | None = None,
    *,
    percent: float | None = None,
    dex: str | None = None,
    usd: bool = False,
    coin_units: bool = False,
) -> ResolvedOrderSize:
    if raw_size is not None and percent is not None:
        raise ValueError("Use either --size or --percent, not both.")
    if raw_size is None and percent is None:
        raise ValueError("Partial close size is required.")

    position = _require_open_position(client, coin, dex=dex)
    market = resolve_market(coin, dex)
    symbol = market.coin.split(":")[-1].upper()
    max_coin_size = abs(position.size)
    max_notional = abs(position.position_value)
    reference_price = _resolve_reference_price(
        client, coin, price=None, dex=dex, symbol=symbol
    )

    resolved_percent = percent
    close_spec: CloseSizeSpec | None = None
    if raw_size is not None:
        close_spec = parse_close_size_spec(
            raw_size,
            coin=coin,
            usd=usd,
            coin_units=coin_units,
        )
        if close_spec.percent is not None:
            resolved_percent = close_spec.percent

    if resolved_percent is not None:
        target_coin = max_coin_size * (resolved_percent / 100)
        sz_decimals = _sz_decimals(client, coin, dex=dex)
        coin_size = round_size_down(target_coin, sz_decimals)
        if coin_size <= 0:
            min_increment = 10**-sz_decimals
            raise HyperliquidClientError(
                f"{resolved_percent:g}% of {symbol} position is too small "
                f"(min increment {min_increment:g} {symbol})."
            )
        if resolved_percent >= 100 or coin_size >= max_coin_size:
            coin_size = max_coin_size
        actual_notional = coin_size * reference_price
        return _build_resolved_close_size(
            position=position,
            coin_size=coin_size,
            actual_notional=actual_notional,
            reference_price=reference_price,
            max_coin_size=max_coin_size,
            symbol=symbol,
            percent=resolved_percent,
        )

    assert close_spec is not None
    if close_spec.coin is not None:
        coin_size = _cap_close_coin_size(
            coin_size=close_spec.coin,
            position=position,
            client=client,
            coin=coin,
            dex=dex,
            symbol=symbol,
        )
        actual_notional = coin_size * reference_price
        return _build_resolved_close_size(
            position=position,
            coin_size=coin_size,
            actual_notional=actual_notional,
            reference_price=reference_price,
            max_coin_size=max_coin_size,
            symbol=symbol,
        )

    assert close_spec.usd_notional is not None
    if close_spec.usd_notional > max_notional + 0.01:
        raise HyperliquidClientError(
            f"Close size {format_usd(close_spec.usd_notional)} exceeds position "
            f"size {format_usd(max_notional)}."
        )
    coin_size, actual_notional = _resolve_usd_notional_size(
        client,
        coin,
        usd_notional=close_spec.usd_notional,
        reference_price=reference_price,
        dex=dex,
        symbol=symbol,
        enforce_min_notional=False,
    )
    coin_size = _cap_close_coin_size(
        coin_size=coin_size,
        position=position,
        client=client,
        coin=coin,
        dex=dex,
        symbol=symbol,
    )
    actual_notional = coin_size * reference_price
    return _build_resolved_close_size(
        position=position,
        coin_size=coin_size,
        actual_notional=actual_notional,
        reference_price=reference_price,
        max_coin_size=max_coin_size,
        symbol=symbol,
    )


def total_positions_notional(positions: list[Position]) -> float:
    return sum(abs(position.position_value) for position in positions)


def total_positions_margin(positions: list[Position]) -> float:
    return sum(position.margin_used for position in positions)


def total_positions_upnl(positions: list[Position]) -> float:
    return sum(position.unrealized_pnl for position in positions)


def total_positions_roe(positions: list[Position]) -> float | None:
    margin = total_positions_margin(positions)
    if margin <= 0:
        return None
    return total_positions_upnl(positions) / margin


def format_total_upnl(positions: list[Position]) -> str:
    return format_pnl(
        total_positions_upnl(positions),
        return_on_equity=total_positions_roe(positions),
    )


def resolve_mark_price(pos: Position, mark_prices: dict[str, float]) -> float | None:
    raw = mark_prices.get(pos.coin)
    if raw is not None:
        return float(raw)
    if pos.size:
        return abs(pos.position_value / pos.size)
    return None


def print_positions_table(
    console: Console,
    positions: list[Position],
    *,
    mark_prices: dict[str, float] | None = None,
    title: str = "Open positions",
) -> None:
    prices = mark_prices or {}
    table = Table(title=title)
    table.add_column("Coin")
    table.add_column("Side")
    table.add_column("Size", justify="right")
    table.add_column("Margin", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Mark", justify="right")
    table.add_column("uPnL", justify="right")
    table.add_column("Lev", justify="right")

    for pos in positions:
        side = "Long" if pos.size > 0 else "Short"
        side_style = "green" if pos.size > 0 else "red"
        entry = format_usd(pos.entry_px) if pos.entry_px is not None else "-"
        mark = resolve_mark_price(pos, prices)
        mark_display = format_usd(mark) if mark is not None else "-"
        upnl = format_pnl(pos.unrealized_pnl, return_on_equity=pos.return_on_equity)
        upnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
        table.add_row(
            pos.coin,
            f"[{side_style}]{side}[/{side_style}]",
            format_size_cell(pos),
            format_margin_cell(pos, mark),
            entry,
            mark_display,
            f"[{upnl_style}]{upnl}[/{upnl_style}]",
            f"{pos.leverage_value}x {pos.leverage_type}",
        )

    console.print()
    console.print(table)


def print_position_detail(
    console: Console,
    pos: Position,
    *,
    mark: float | None,
) -> None:
    mark_prices = {pos.coin: mark} if mark is not None else {}
    print_positions_table(
        console,
        [pos],
        mark_prices=mark_prices,
        title=f"{position_coin_symbol(pos.coin)} position",
    )
