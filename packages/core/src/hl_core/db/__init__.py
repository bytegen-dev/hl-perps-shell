"""Database layer for hl-perps-shell."""

from hl_core.db.crypto import decrypt_secret, encrypt_secret, generate_encryption_key
from hl_core.db.engine import get_engine, init_database
from hl_core.db.exceptions import (
    WalletDatabaseNotConfiguredError,
    WalletEncryptionNotConfiguredError,
    WalletStoreError,
)
from hl_core.db.store import WalletRecord, WalletStore

__all__ = [
    "WalletStore",
    "WalletRecord",
    "WalletStoreError",
    "WalletEncryptionNotConfiguredError",
    "WalletDatabaseNotConfiguredError",
    "init_database",
    "get_engine",
    "encrypt_secret",
    "decrypt_secret",
    "generate_encryption_key",
]
