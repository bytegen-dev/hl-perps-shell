from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Position:
    coin: str
    size: float
    entry_px: float | None
    unrealized_pnl: float
    return_on_equity: float
    liquidation_px: float | None
    margin_used: float
    position_value: float
    leverage_type: str
    leverage_value: int
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SpotBalance:
    coin: str
    total: float
    hold: float

    @property
    def available(self) -> float:
        return max(self.total - self.hold, 0.0)


@dataclass(frozen=True, slots=True)
class AccountSummary:
    account_value: float
    total_margin_used: float
    total_notional: float
    withdrawable: float
    spot_usdc_total: float
    spot_usdc_hold: float
    spot_usdc_available: float
    raw: dict[str, Any]
    spot_raw: dict[str, Any]

    @property
    def tradable_usdc(self) -> float:
        """USDC available for trading in unified / spot clearinghouse."""
        return self.spot_usdc_available


@dataclass(frozen=True, slots=True)
class OrderResult:
    status: str
    raw: dict[str, Any]

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True, slots=True)
class GeneratedWallet:
    address: str
    private_key: str

    @property
    def private_key_hex(self) -> str:
        if self.private_key.startswith("0x"):
            return self.private_key
        return f"0x{self.private_key}"


@dataclass(frozen=True, slots=True)
class ApprovedAgentWallet:
    address: str
    private_key: str
    approval_result: dict[str, Any]

    @property
    def private_key_hex(self) -> str:
        if self.private_key.startswith("0x"):
            return self.private_key
        return f"0x{self.private_key}"
