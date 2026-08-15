from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from hl_core.config import HyperliquidSettings, get_settings
from hl_core.db.crypto import decrypt_secret, encrypt_secret
from hl_core.db.engine import get_session_factory, init_database
from hl_core.db.exceptions import WalletStoreError
from hl_core.db.models import StoredWallet

WalletKind = Literal["evm", "agent"]


@dataclass(frozen=True, slots=True)
class WalletRecord:
    id: str
    address: str
    kind: str
    network: str | None
    label: str | None
    master_account: str | None
    file_path: str | None
    created_at: datetime


class WalletStore:
    """Encrypted Postgres-backed wallet registry."""

    def __init__(self, settings: HyperliquidSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session_factory = get_session_factory(self.settings.database_url)

    def init_db(self) -> None:
        init_database(self.settings.database_url)

    def save_wallet(
        self,
        *,
        address: str,
        private_key: str,
        kind: WalletKind,
        network: str | None = None,
        label: str | None = None,
        master_account: str | None = None,
        file_path: Path | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WalletRecord:
        self.init_db()
        encryption_key = self.settings.require_wallet_encryption_key()
        encrypted_private_key = encrypt_secret(private_key, encryption_key)
        normalized_address = address.lower()

        with self._session_factory() as session:
            existing = session.scalar(
                select(StoredWallet).where(StoredWallet.address == normalized_address)
            )
            if existing is not None:
                existing.encrypted_private_key = encrypted_private_key
                existing.kind = kind
                existing.network = network
                existing.label = label
                existing.master_account = master_account
                existing.file_path = str(file_path) if file_path is not None else None
                existing.metadata_json = metadata
                session.commit()
                session.refresh(existing)
                return _to_record(existing)

            record = StoredWallet(
                address=normalized_address,
                encrypted_private_key=encrypted_private_key,
                kind=kind,
                network=network,
                label=label,
                master_account=master_account,
                file_path=str(file_path) if file_path is not None else None,
                metadata_json=metadata,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise WalletStoreError(f"Wallet already exists for address {address}.") from exc
            session.refresh(record)
            return _to_record(record)

    def list_wallets(self) -> list[WalletRecord]:
        self.init_db()
        with self._session_factory() as session:
            rows = session.scalars(select(StoredWallet).order_by(StoredWallet.created_at.desc()))
            return [_to_record(row) for row in rows.all()]

    def get_private_key(self, address: str) -> str:
        self.init_db()
        encryption_key = self.settings.require_wallet_encryption_key()
        normalized_address = address.lower()

        with self._session_factory() as session:
            row = session.scalar(
                select(StoredWallet).where(StoredWallet.address == normalized_address)
            )
            if row is None:
                raise WalletStoreError(f"No wallet found for address {address}.")
            return decrypt_secret(row.encrypted_private_key, encryption_key)


def _to_record(row: StoredWallet) -> WalletRecord:
    return WalletRecord(
        id=str(row.id),
        address=row.address,
        kind=row.kind,
        network=row.network,
        label=row.label,
        master_account=row.master_account,
        file_path=row.file_path,
        created_at=row.created_at,
    )
