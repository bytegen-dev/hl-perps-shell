from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from hl_core.db.store import WalletStore

from hl_client.types import GeneratedWallet
from hl_client.wallets import load_wallet_file

WalletKind = Literal["evm", "agent"]


def persist_wallet_to_db(
    wallet: GeneratedWallet,
    *,
    kind: WalletKind,
    network: str | None = None,
    label: str | None = None,
    master_account: str | None = None,
    file_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    store = WalletStore()
    store.save_wallet(
        address=wallet.address,
        private_key=wallet.private_key_hex,
        kind=kind,
        network=network,
        label=label,
        master_account=master_account,
        file_path=file_path,
        metadata=metadata,
    )


def import_wallet_file_to_db(path: Path, *, label: str | None = None) -> None:
    wallet = load_wallet_file(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    kind = payload.get("kind", "evm")
    if kind not in {"evm", "agent"}:
        kind = "evm"

    persist_wallet_to_db(
        wallet,
        kind=kind,
        network=payload.get("network"),
        label=label or payload.get("label"),
        master_account=payload.get("master_account"),
        file_path=path,
        metadata={k: v for k, v in payload.items() if k not in {"private_key", "address"}},
    )
