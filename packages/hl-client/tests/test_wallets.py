from pathlib import Path

import pytest
from hl_client.wallets import (
    generate_wallet,
    load_wallet_file,
    normalize_eth_address,
    save_wallet_file,
    wallet_from_private_key,
)


def test_generate_wallet_format() -> None:
    wallet = generate_wallet()
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42
    assert wallet.private_key_hex.startswith("0x")


def test_normalize_eth_address() -> None:
    address = normalize_eth_address("0x" + "ab" * 20)
    assert address == "0x" + "ab" * 20


def test_normalize_eth_address_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_eth_address("not-an-address")


def test_save_and_load_wallet_file(tmp_path: Path) -> None:
    wallet = generate_wallet()
    path = tmp_path / "wallet.json"
    save_wallet_file(path, wallet, network="testnet")
    loaded = load_wallet_file(path)
    assert loaded.address == wallet.address
    assert loaded.private_key_hex == wallet.private_key_hex


def test_wallet_from_private_key_round_trip() -> None:
    source = generate_wallet()
    imported = wallet_from_private_key(source.private_key_hex)
    assert imported.address == source.address
    assert imported.private_key_hex == source.private_key_hex


def test_wallet_from_private_key_accepts_no_prefix() -> None:
    source = generate_wallet()
    raw = source.private_key_hex.removeprefix("0x")
    imported = wallet_from_private_key(raw)
    assert imported.address == source.address


def test_wallet_from_private_key_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        wallet_from_private_key("not-a-key")
