from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import eth_account

from hl_client.types import GeneratedWallet

_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ETH_PRIVATE_KEY_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")


def normalize_eth_address(address: str) -> str:
    address = address.strip()
    if not _ETH_ADDRESS_RE.fullmatch(address):
        raise ValueError("Address must be a 0x-prefixed 42-character hex string.")
    return address


def generate_wallet() -> GeneratedWallet:
    """Create a new random EVM wallet."""
    account = eth_account.Account.create()
    private_key = account.key.hex()
    if not private_key.startswith("0x"):
        private_key = f"0x{private_key}"
    return GeneratedWallet(address=account.address, private_key=private_key)


def wallet_from_private_key(private_key: str) -> GeneratedWallet:
    """Derive an EVM wallet address from an existing private key."""
    raw = private_key.strip()
    if not raw:
        raise ValueError("Private key is required.")
    if not _ETH_PRIVATE_KEY_RE.fullmatch(raw):
        raise ValueError("Private key must be a 32-byte hex string (with or without 0x prefix).")

    key_hex = raw if raw.startswith("0x") else f"0x{raw}"
    try:
        account = eth_account.Account.from_key(key_hex)
    except Exception as exc:
        raise ValueError("Invalid private key.") from exc

    return GeneratedWallet(address=account.address, private_key=key_hex)


def save_wallet_file(
    path: Path,
    wallet: GeneratedWallet,
    *,
    kind: Literal["evm", "agent"] = "evm",
    network: str | None = None,
    overwrite: bool = False,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Persist wallet credentials to disk with restrictive permissions."""
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Wallet file already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "address": wallet.address,
        "private_key": wallet.private_key_hex,
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if network is not None:
        payload["network"] = network
    if extra:
        payload.update(extra)

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def load_wallet_file(path: Path) -> GeneratedWallet:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GeneratedWallet(
        address=normalize_eth_address(payload["address"]),
        private_key=str(payload["private_key"]),
    )
