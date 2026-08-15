from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Network = Literal["mainnet", "testnet"]

MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"


class HyperliquidSettings(BaseSettings):
    """Hyperliquid connection settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_prefix="HL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    network: Network = "testnet"
    account_address: str | None = None
    secret_key: SecretStr | None = None
    skip_ws: bool = True
    database_url: str | None = "postgresql+psycopg://hlxfgen:hlxfgen@localhost:5440/hlxfgen"
    wallet_encryption_key: SecretStr | None = None

    @field_validator("account_address")
    @classmethod
    def normalize_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.startswith("0x"):
            raise ValueError("account_address must be a 0x-prefixed hex address")
        return value

    @property
    def api_url(self) -> str:
        if self.network == "mainnet":
            return MAINNET_API_URL
        return TESTNET_API_URL

    def resolved_account_address(self, signer_address: str | None = None) -> str:
        """Return the master account address used for queries and trading."""
        if self.account_address:
            return self.account_address
        if signer_address:
            return signer_address
        raise ValueError(
            "Set HL_ACCOUNT_ADDRESS or HL_SECRET_KEY so an account address can be resolved."
        )

    def require_secret_key(self) -> str:
        if self.secret_key is None:
            raise ValueError(
                "HL_SECRET_KEY is required for trading actions. "
                "Prefer an API/agent wallet key over your main wallet."
            )
        return self.secret_key.get_secret_value()

    def require_wallet_encryption_key(self) -> str:
        if self.wallet_encryption_key is None:
            raise ValueError(
                "HL_WALLET_ENCRYPTION_KEY is required to store wallets in Postgres. "
                "Run `hl db generate-key` to create one."
            )
        return self.wallet_encryption_key.get_secret_value()


@lru_cache
def get_settings() -> HyperliquidSettings:
    return HyperliquidSettings()
