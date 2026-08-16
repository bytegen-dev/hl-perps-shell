from __future__ import annotations

from typing import Any, Literal

import eth_account
from hl_core.config import HyperliquidSettings, get_settings
from hyperliquid.api import API
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import OrderRequest

from hl_client.exceptions import HyperliquidClientError, TradingNotConfiguredError
from hl_client.markets import PerpMarket, ResolvedMarket, resolve_market
from hl_client.tpsl import TpslKind
from hl_client.types import AccountSummary, ApprovedAgentWallet, OrderResult, Position, SpotBalance
from hl_client.wallets import normalize_eth_address

TimeInForce = Literal["Gtc", "Ioc", "Alo"]


def _to_float(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _spot_usdc_amounts(spot_state: dict[str, Any]) -> tuple[float, float, float]:
    for item in spot_state.get("balances", []):
        if item.get("coin") == "USDC":
            total = _to_float(item.get("total"))
            hold = _to_float(item.get("hold"))
            return total, hold, max(total - hold, 0.0)
    return 0.0, 0.0, 0.0


def _parse_position(raw: dict[str, Any]) -> Position:
    position = raw["position"]
    leverage = position["leverage"]
    return Position(
        coin=position["coin"],
        size=_to_float(position["szi"]),
        entry_px=_to_float(position["entryPx"]) if position.get("entryPx") else None,
        unrealized_pnl=_to_float(position["unrealizedPnl"]),
        return_on_equity=_to_float(position["returnOnEquity"]),
        liquidation_px=_to_float(position["liquidationPx"])
        if position.get("liquidationPx")
        else None,
        margin_used=_to_float(position["marginUsed"]),
        position_value=_to_float(position["positionValue"]),
        leverage_type=leverage["type"],
        leverage_value=int(leverage["value"]),
        raw=raw,
    )


def _extract_portfolio_pnl(portfolio: list[Any], period: str) -> float | None:
    for entry in portfolio:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        key, data = entry
        if key != period or not isinstance(data, dict):
            continue
        history = data.get("pnlHistory", [])
        if not history:
            return 0.0
        latest = history[-1]
        if not isinstance(latest, list) or len(latest) != 2:
            return None
        return _to_float(latest[1])
    return None


class HyperliquidClient:
    """Typed wrapper around the official Hyperliquid Python SDK."""

    def __init__(
        self,
        settings: HyperliquidSettings,
        *,
        info: Info | None,
        exchange: Exchange | None,
        account_address: str,
        signer_address: str | None = None,
    ) -> None:
        self.settings = settings
        self._info_by_dex: dict[str, Info] = {}
        if info is not None:
            self._info_by_dex[""] = info
        self._api: API | None = None
        self.exchange = exchange
        self.account_address = account_address
        self.signer_address = signer_address or account_address

    @property
    def info(self) -> Info:
        """Native Hyperliquid dex Info instance."""
        from hl_client.dex import get_info_for_dex

        return get_info_for_dex(self, "")

    def _api_client(self) -> API:
        if self._api is None:
            self._api = API(self.settings.api_url)
        return self._api

    def _resolve_market(self, coin: str, dex: str | None = None) -> ResolvedMarket:
        return resolve_market(coin, dex)

    @classmethod
    def from_settings(cls, settings: HyperliquidSettings | None = None) -> HyperliquidClient:
        settings = settings or get_settings()
        info = Info(settings.api_url, skip_ws=settings.skip_ws)

        exchange: Exchange | None = None
        signer_address: str | None = None

        if settings.secret_key is not None:
            account = eth_account.Account.from_key(settings.require_secret_key())
            signer_address = account.address
            master_address = settings.resolved_account_address(signer_address)
            exchange = Exchange(
                account,
                settings.api_url,
                account_address=master_address,
            )
            account_address = master_address
        else:
            if settings.account_address:
                account_address = settings.account_address
            else:
                account_address = ""

        return cls(
            settings,
            info=info,
            exchange=exchange,
            account_address=account_address,
            signer_address=signer_address,
        )

    @classmethod
    def readonly(cls, settings: HyperliquidSettings | None = None) -> HyperliquidClient:
        """Create a read-only client (market data only, no account address required)."""
        settings = settings or get_settings()
        return cls(
            settings,
            info=None,
            exchange=None,
            account_address=settings.account_address or "",
        )

    def require_account_address(self) -> str:
        if not self.account_address:
            raise HyperliquidClientError(
                "Account address is required. Set HL_ACCOUNT_ADDRESS or HL_SECRET_KEY."
            )
        return self.account_address

    def require_exchange(self) -> Exchange:
        if self.exchange is None:
            raise TradingNotConfiguredError(
                "Trading is not configured. Set HL_SECRET_KEY (prefer an API/agent wallet)."
            )
        return self.exchange

    # --- Market data ---

    def list_perp_dexs(self) -> list[str]:
        dexs = self._api_client().post("/info", {"type": "perpDexs"})
        names: list[str] = []
        for item in dexs:
            if item is None:
                continue
            names.append(str(item["name"]))
        return names

    def get_all_mids(self, *, dex: str | None = None) -> dict[str, str]:
        dex_key = dex or ""
        return self._api_client().post("/info", {"type": "allMids", "dex": dex_key})

    def get_perp_mids(self, *, dex: str | None = None) -> dict[str, str]:
        """Return mids for perpetual markets only (excludes spot @ pairs and # markets)."""
        all_mids = self.get_all_mids(dex=dex)
        meta = self.get_meta(dex=dex)
        perp_names = {asset["name"] for asset in meta["universe"]}
        return {name: mid for name, mid in all_mids.items() if name in perp_names}

    def get_mid(self, coin: str, *, dex: str | None = None) -> float | None:
        market = self._resolve_market(coin, dex)
        mids = self.get_all_mids(dex=market.dex or None)
        mid = mids.get(market.coin)
        return float(mid) if mid is not None else None

    def get_meta(self, *, dex: str | None = None) -> dict[str, Any]:
        dex_key = dex or ""
        return self._api_client().post("/info", {"type": "meta", "dex": dex_key})

    def get_perp_dexs(self) -> list[Any]:
        return self._api_client().post("/info", {"type": "perpDexs"})

    def get_all_perp_metas(self) -> list[Any]:
        return self._api_client().post("/info", {"type": "allPerpMetas"})

    def list_perp_markets(self) -> list[PerpMarket]:
        from hl_client.markets import parse_perp_markets

        return parse_perp_markets(dexs=self.get_perp_dexs(), metas=self.get_all_perp_metas())

    def get_meta_and_asset_ctxs(self) -> Any:
        return self.info.meta_and_asset_ctxs()

    def get_candles(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        *,
        dex: str | None = None,
    ) -> list[dict[str, Any]]:
        market = self._resolve_market(coin, dex)
        req = {
            "coin": market.coin,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        return self._api_client().post("/info", {"type": "candleSnapshot", "req": req})

    def get_funding_history(
        self,
        coin: str,
        start_ms: int,
        end_ms: int | None = None,
        *,
        dex: str | None = None,
    ) -> list[dict[str, Any]]:
        market = self._resolve_market(coin, dex)
        payload: dict[str, Any] = {
            "type": "fundingHistory",
            "coin": market.coin,
            "startTime": start_ms,
        }
        if end_ms is not None:
            payload["endTime"] = end_ms
        return self._api_client().post("/info", payload)

    # --- Account ---

    def get_user_state(self) -> dict[str, Any]:
        return self.info.user_state(self.require_account_address())

    def get_spot_clearinghouse_state(self) -> dict[str, Any]:
        return self._api_client().post(
            "/info",
            {"type": "spotClearinghouseState", "user": self.require_account_address()},
        )

    def get_spot_balances(self) -> list[SpotBalance]:
        balances: list[SpotBalance] = []
        for item in self.get_spot_clearinghouse_state().get("balances", []):
            balances.append(
                SpotBalance(
                    coin=str(item["coin"]),
                    total=_to_float(item.get("total")),
                    hold=_to_float(item.get("hold")),
                )
            )
        return balances

    def get_account_summary(self) -> AccountSummary:
        state = self.get_user_state()
        spot_state = self.get_spot_clearinghouse_state()
        margin = state["marginSummary"]
        spot_usdc_total, spot_usdc_hold, spot_usdc_available = _spot_usdc_amounts(spot_state)
        return AccountSummary(
            account_value=_to_float(margin["accountValue"]),
            total_margin_used=_to_float(margin["totalMarginUsed"]),
            total_notional=_to_float(margin["totalNtlPos"]),
            withdrawable=_to_float(state["withdrawable"]),
            spot_usdc_total=spot_usdc_total,
            spot_usdc_hold=spot_usdc_hold,
            spot_usdc_available=spot_usdc_available,
            raw=state,
            spot_raw=spot_state,
        )

    def get_positions(self) -> list[Position]:
        state = self.get_user_state()
        positions: list[Position] = []
        for asset_position in state["assetPositions"]:
            position = asset_position["position"]
            if _to_float(position["szi"]) == 0.0:
                continue
            positions.append(_parse_position(asset_position))
        return positions

    def get_position(self, coin: str, *, dex: str | None = None) -> Position | None:
        market = self._resolve_market(coin, dex)
        for position in self.get_positions():
            if position.coin == market.coin:
                return position
        return None

    def get_active_asset_data(self, coin: str, *, dex: str | None = None) -> dict[str, Any]:
        market = self._resolve_market(coin, dex)
        return self._api_client().post(
            "/info",
            {
                "type": "activeAssetData",
                "user": self.require_account_address(),
                "coin": market.coin,
            },
        )

    def get_open_orders(self) -> list[dict[str, Any]]:
        return self.info.open_orders(self.require_account_address())

    def get_user_fills(self) -> list[dict[str, Any]]:
        return self.info.user_fills(self.require_account_address())

    def get_portfolio(self) -> list[Any]:
        return self._api_client().post(
            "/info",
            {"type": "portfolio", "user": self.require_account_address()},
        )

    def get_all_time_pnl(self) -> float:
        pnl = _extract_portfolio_pnl(self.get_portfolio(), "allTime")
        if pnl is None:
            raise HyperliquidClientError("Portfolio response missing allTime PnL.")
        return pnl

    # --- Trading ---

    def update_leverage(self, coin: str, leverage: int, *, is_cross: bool = False) -> Any:
        return self.require_exchange().update_leverage(leverage, coin.upper(), is_cross)

    def place_limit_order(
        self,
        coin: str,
        *,
        is_buy: bool,
        size: float,
        price: float,
        tif: TimeInForce = "Gtc",
        reduce_only: bool = False,
    ) -> OrderResult:
        order_type = {"limit": {"tif": tif}}
        raw = self.require_exchange().order(
            coin.upper(),
            is_buy,
            size,
            price,
            order_type,
            reduce_only=reduce_only,
        )
        return OrderResult(status=raw.get("status", "unknown"), raw=raw)

    def cancel_order(self, coin: str, oid: int) -> Any:
        return self.require_exchange().cancel(coin.upper(), oid)

    def place_position_tpsl(
        self,
        coin: str,
        *,
        kind: TpslKind,
        trigger_px: float,
        size: float,
        limit_px: float | None = None,
        is_market: bool = True,
    ) -> OrderResult:
        """Place a position-linked take-profit or stop-loss trigger order."""
        position = self.get_position(coin)
        if position is None:
            raise HyperliquidClientError(f"No open position for {coin.upper()}.")

        if size <= 0:
            raise HyperliquidClientError("TP/SL size must be positive.")
        if size > abs(position.size) + 1e-12:
            raise HyperliquidClientError(
                f"TP/SL size {size:g} exceeds position size {abs(position.size):g}."
            )
        if trigger_px <= 0:
            raise HyperliquidClientError("Trigger price must be positive.")

        is_buy = position.size < 0
        exec_limit_px = limit_px if limit_px is not None else trigger_px
        order: OrderRequest = {
            "coin": coin.upper(),
            "is_buy": is_buy,
            "sz": size,
            "limit_px": exec_limit_px,
            "order_type": {
                "trigger": {
                    "triggerPx": trigger_px,
                    "isMarket": is_market,
                    "tpsl": kind,
                }
            },
            "reduce_only": True,
        }
        raw = self.require_exchange().bulk_orders([order], grouping="positionTpsl")
        return OrderResult(status=raw.get("status", "unknown"), raw=raw)

    def market_open(
        self,
        coin: str,
        *,
        is_buy: bool,
        size: float,
        slippage: float = 0.05,
    ) -> OrderResult:
        raw = self.require_exchange().market_open(coin.upper(), is_buy, size, slippage=slippage)
        return OrderResult(status=raw.get("status", "unknown"), raw=raw)

    def market_close(
        self,
        coin: str,
        *,
        size: float | None = None,
        slippage: float = 0.05,
    ) -> OrderResult:
        raw = self.require_exchange().market_close(coin.upper(), sz=size, slippage=slippage)
        return OrderResult(status=raw.get("status", "unknown"), raw=raw)

    # --- Transfers & withdrawals ---

    def withdraw_to_arbitrum(self, amount: float, destination: str) -> dict[str, Any]:
        """Withdraw USDC from Hyperliquid to an external address (bridge)."""
        dest = normalize_eth_address(destination)
        if amount <= 0:
            raise HyperliquidClientError("Withdraw amount must be positive.")

        summary = self.get_account_summary()
        if amount > summary.withdrawable:
            raise HyperliquidClientError(
                f"Withdraw amount ${amount:,.2f} exceeds withdrawable "
                f"${summary.withdrawable:,.2f}."
            )

        raw = self.require_exchange().withdraw_from_bridge(amount, dest)
        if isinstance(raw, dict):
            return raw
        return {"status": "unknown", "response": raw}

    def send_usd(self, amount: float, destination: str) -> dict[str, Any]:
        """Send USD to another Hyperliquid account (internal transfer)."""
        dest = normalize_eth_address(destination)
        if amount <= 0:
            raise HyperliquidClientError("Transfer amount must be positive.")

        raw = self.require_exchange().usd_transfer(amount, dest)
        if isinstance(raw, dict):
            return raw
        return {"status": "unknown", "response": raw}

    def approve_agent_wallet(self, name: str | None = None) -> ApprovedAgentWallet:
        """Generate and approve a new Hyperliquid API/agent wallet."""
        raw_result, agent_key = self.require_exchange().approve_agent(name)
        account = eth_account.Account.from_key(agent_key)
        private_key = agent_key if agent_key.startswith("0x") else f"0x{agent_key}"
        result = raw_result if isinstance(raw_result, dict) else {"response": raw_result}
        return ApprovedAgentWallet(
            address=account.address,
            private_key=private_key,
            approval_result=result,
        )
