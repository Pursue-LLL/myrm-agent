"""Tests for wecom/crypto module — WeComCrypto encrypt/decrypt/verify."""

from __future__ import annotations

import base64

import pytest

from app.channels.providers.wecom.crypto import WeComCrypto

_TEST_KEY = base64.b64encode(b"0" * 32).decode().rstrip("=")
_TEST_TOKEN = "test_token"
_TEST_CORP_ID = "test_corp"


def _make_crypto() -> WeComCrypto:
    return WeComCrypto(_TEST_TOKEN, _TEST_KEY, _TEST_CORP_ID)


class TestWeComCrypto:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        crypto = _make_crypto()
        plaintext = "<xml><Content>Hello</Content></xml>"
        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == plaintext

    def test_decrypt_wrong_corp_id(self) -> None:
        crypto = _make_crypto()
        other_crypto = WeComCrypto(_TEST_TOKEN, _TEST_KEY, "wrong_corp")
        encrypted = crypto.encrypt("test message")
        with pytest.raises(ValueError, match="Corp ID mismatch"):
            other_crypto.decrypt(encrypted)

    def test_verify_signature_valid(self) -> None:
        import time

        crypto = _make_crypto()
        encrypted = crypto.encrypt("test")
        import hashlib

        ts = str(int(time.time()))
        items = sorted([_TEST_TOKEN, ts, "nonce123", encrypted])
        expected_sig = hashlib.sha1("".join(items).encode()).hexdigest()
        assert crypto.verify_signature(expected_sig, ts, "nonce123", encrypted) is True

    def test_verify_signature_invalid(self) -> None:
        crypto = _make_crypto()
        encrypted = crypto.encrypt("test")
        assert crypto.verify_signature("wrong_signature", "1234567890", "nonce123", encrypted) is False

    def test_extract_encrypted_from_xml(self) -> None:
        xml = "<xml><Encrypt>abc123</Encrypt></xml>"
        assert WeComCrypto.extract_encrypted_from_xml(xml) == "abc123"

    def test_extract_encrypted_from_xml_missing(self) -> None:
        xml = "<xml><Other>data</Other></xml>"
        with pytest.raises(ValueError, match="Missing <Encrypt>"):
            WeComCrypto.extract_encrypted_from_xml(xml)

    def test_encrypt_produces_base64(self) -> None:
        crypto = _make_crypto()
        encrypted = crypto.encrypt("hello")
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 0

    def test_encrypt_different_each_time(self) -> None:
        crypto = _make_crypto()
        e1 = crypto.encrypt("same message")
        e2 = crypto.encrypt("same message")
        assert e1 != e2
