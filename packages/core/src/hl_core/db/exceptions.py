class WalletStoreError(Exception):
    """Base error for wallet persistence."""


class WalletEncryptionNotConfiguredError(WalletStoreError):
    """Raised when HL_WALLET_ENCRYPTION_KEY is missing."""


class WalletDatabaseNotConfiguredError(WalletStoreError):
    """Raised when HL_DATABASE_URL is missing."""
