from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from hl_core.db.exceptions import WalletEncryptionNotConfiguredError


def derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, encryption_key: str) -> str:
    if not encryption_key.strip():
        raise WalletEncryptionNotConfiguredError(
            "Set HL_WALLET_ENCRYPTION_KEY before storing wallets in Postgres."
        )
    fernet = Fernet(derive_fernet_key(encryption_key))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, encryption_key: str) -> str:
    if not encryption_key.strip():
        raise WalletEncryptionNotConfiguredError(
            "Set HL_WALLET_ENCRYPTION_KEY before reading wallets from Postgres."
        )
    fernet = Fernet(derive_fernet_key(encryption_key))
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt wallet. Check HL_WALLET_ENCRYPTION_KEY.") from exc


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")
