"""Tests for _decrypt_if_needed fallback and double-encryption handling."""

import os

import pytest
from myrm_agent_harness.utils.crypto import ConfigCrypto


@pytest.fixture(autouse=True)
def setup_local_mode():
    """Force Local mode for these tests."""
    original = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"

    import app.services.config.encryption as enc_mod

    enc_mod._encryption_service = None

    yield

    enc_mod._encryption_service = None
    if original:
        os.environ["DEPLOY_MODE"] = original
    else:
        os.environ.pop("DEPLOY_MODE", None)


def _make_config(key: str, value: object, is_encrypted: bool):
    """Create a mock UserConfig-like object."""

    class FakeConfig:
        config_key = key
        config_value = value

    FakeConfig.is_encrypted = is_encrypted
    return FakeConfig()


class TestDecryptIfNeeded:
    def test_unencrypted_dict_returned_as_is(self):
        from app.services.config.service import _decrypt_if_needed

        cfg = _make_config("chatSettings", {"theme": "dark"}, is_encrypted=False)
        result = _decrypt_if_needed(cfg)
        assert result == {"theme": "dark"}

    def test_unencrypted_non_dict_returns_empty(self):
        from app.services.config.service import _decrypt_if_needed

        cfg = _make_config("chatSettings", "not-a-dict", is_encrypted=False)
        result = _decrypt_if_needed(cfg)
        assert result == {}

    def test_normal_decryption(self):
        from app.services.config.encryption import get_encryption_service
        from app.services.config.service import _decrypt_if_needed

        svc = get_encryption_service()
        plaintext = {"api_key": "sk-test"}
        cipher = ConfigCrypto.encrypt_value(plaintext, svc.raw_key)

        cfg = _make_config("providers", {"_cipher": cipher}, is_encrypted=True)
        result = _decrypt_if_needed(cfg)
        assert result == plaintext

    def test_string_cipher_format(self):
        from app.services.config.encryption import get_encryption_service
        from app.services.config.service import _decrypt_if_needed

        svc = get_encryption_service()
        plaintext = {"model": "gpt-4"}
        cipher = ConfigCrypto.encrypt_value(plaintext, svc.raw_key)

        cfg = _make_config("providers", cipher, is_encrypted=True)
        result = _decrypt_if_needed(cfg)
        assert result == plaintext

    def test_double_encrypted_data(self):
        from app.services.config.encryption import get_encryption_service
        from app.services.config.service import _decrypt_if_needed

        svc = get_encryption_service()
        plaintext = {"api_key": "sk-real"}
        inner_cipher = ConfigCrypto.encrypt_value(plaintext, svc.raw_key)
        outer_cipher = ConfigCrypto.encrypt_value({"_cipher": inner_cipher}, svc.raw_key)

        cfg = _make_config("providers", {"_cipher": outer_cipher}, is_encrypted=True)
        result = _decrypt_if_needed(cfg)
        assert result == plaintext


class TestLegacyFingerprintFallback:
    def test_fallback_to_fingerprint_key(self):
        from app.services.config.encryption import get_encryption_service
        from app.services.config.service import _decrypt_if_needed

        svc = get_encryption_service()

        from myrm_agent_harness.utils import derive_key_from_fingerprint, get_device_fingerprint

        fp = get_device_fingerprint()
        legacy_key = derive_key_from_fingerprint(fp)

        if legacy_key == svc.raw_key:
            pytest.skip("Current key equals legacy key (same derivation), can't test fallback")

        plaintext = {"api_key": "sk-legacy"}
        cipher = ConfigCrypto.encrypt_value(plaintext, legacy_key)

        cfg = _make_config("providers", {"_cipher": cipher}, is_encrypted=True)
        result = _decrypt_if_needed(cfg)
        assert result == plaintext


class TestEncryptIfSensitiveGuard:
    def test_already_encrypted_envelope_skipped(self):
        from app.services.config.service import _encrypt_if_sensitive

        cipher_envelope = {"_cipher": "some-base64-ciphertext"}
        result, is_encrypted = _encrypt_if_sensitive("providers", cipher_envelope)
        assert is_encrypted is True
        assert result == cipher_envelope

    def test_normal_value_gets_encrypted(self):
        from app.services.config.service import _encrypt_if_sensitive

        value = {"api_key": "sk-test", "enabled": True}
        result, is_encrypted = _encrypt_if_sensitive("providers", value)
        assert is_encrypted is True
        assert isinstance(result, str)
        assert result != value
