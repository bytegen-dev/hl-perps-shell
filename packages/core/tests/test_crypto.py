from hl_core.db.crypto import decrypt_secret, encrypt_secret, generate_encryption_key


def test_encrypt_decrypt_roundtrip() -> None:
    key = generate_encryption_key()
    plaintext = "0xdeadbeef"
    ciphertext = encrypt_secret(plaintext, key)
    assert decrypt_secret(ciphertext, key) == plaintext
    assert ciphertext != plaintext


def test_generate_encryption_key_format() -> None:
    key = generate_encryption_key()
    assert isinstance(key, str)
    assert len(key) > 20
