"""Tests for Local mode config encryption."""

import os

import pytest


@pytest.fixture(autouse=True)
def setup_local_mode():
    """Force Local mode for these tests."""
    original = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    yield
    if original:
        os.environ["DEPLOY_MODE"] = original
    else:
        del os.environ["DEPLOY_MODE"]


def test_local_mode_encryption_service():
    """Test that Local mode encryption service initializes with a valid key."""
    from app.services.config.encryption import get_encryption_service, is_sensitive_config

    svc = get_encryption_service()

    assert svc._is_local is True
    assert svc._is_sandbox is False
    assert svc._key is not None
    assert len(svc._key) == 32

    assert svc.should_encrypt("providers") is True
    assert svc.should_encrypt("chatSettings") is False

    assert is_sensitive_config("providers") is True
    assert is_sensitive_config("retrieval") is True
    assert is_sensitive_config("chatSettings") is False


def test_local_mode_encrypt_decrypt():
    """Test encryption/decryption in Local mode."""
    from app.services.config.encryption import get_encryption_service

    svc = get_encryption_service()

    test_providers = {
        "openai": {
            "enabled": True,
            "api_key": "sk-test-123",
            "models": [{"name": "gpt-4"}],
        }
    }

    encrypted_value, is_encrypted = svc.encrypt_if_needed("providers", test_providers)

    assert is_encrypted is True
    assert isinstance(encrypted_value, str)
    assert encrypted_value != test_providers

    decrypted = svc.decrypt(encrypted_value)
    assert decrypted == test_providers


def test_local_mode_non_sensitive_not_encrypted():
    """Test that non-sensitive configs are not encrypted in Local mode."""
    from app.services.config.encryption import get_encryption_service

    svc = get_encryption_service()

    test_settings = {
        "theme": "dark",
        "language": "en",
    }

    result, is_encrypted = svc.encrypt_if_needed("chatSettings", test_settings)

    assert is_encrypted is False
    assert result == test_settings


def test_device_fingerprint_stable():
    """Test that device fingerprint is stable across service reloads."""
    from myrm_agent_harness.utils import get_device_fingerprint

    fp1 = get_device_fingerprint()
    fp2 = get_device_fingerprint()

    assert fp1 == fp2
    assert len(fp1) == 64


@pytest.mark.asyncio
async def test_migrate_configs_with_recovery_key():
    """Test migration of configs with recovery key."""
    from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto

    from app.services.config.encryption import get_encryption_service
    from app.services.config.migration import migrate_configs_with_recovery_key

    class MockConfig:
        def __init__(self, key, value):
            self.id = 1
            self.config_key = key
            self.config_value = value
            self.version = 1

    class MockResult:
        def __init__(self, configs):
            self._configs = configs

        def scalars(self):
            class Scalars:
                def all(self_inner):
                    return self._configs

            return Scalars()

    class MockSession:
        def __init__(self, configs):
            self._configs = configs
            self.committed = False

        async def execute(self, query):
            return MockResult(self._configs)

        async def commit(self):
            self.committed = True

    svc = get_encryption_service()
    current_key = svc._key
    assert current_key is not None

    old_key = os.urandom(32)

    # Config 1: Plaintext (should be skipped)
    cfg1 = MockConfig("providers", {"api_key": "plain"})
    # Config 2: Encrypted with current key (should be skipped)
    cfg2_val = ConfigCrypto.encrypt_value({"api_key": "current"}, current_key)
    cfg2 = MockConfig("retrieval", cfg2_val)
    # Config 3: Encrypted with old key (should be migrated)
    cfg3_val = ConfigCrypto.encrypt_value({"api_key": "old"}, old_key)
    cfg3 = MockConfig("searchServices", cfg3_val)
    # Config 4: Encrypted with some other key (should fail)
    cfg4_val = ConfigCrypto.encrypt_value({"api_key": "other"}, os.urandom(32))
    cfg4 = MockConfig("mcpServers", cfg4_val)

    db = MockSession([cfg1, cfg2, cfg3, cfg4])

    stats = await migrate_configs_with_recovery_key(db, old_key)

    assert stats["migrated"] == 1
    assert stats["skipped"] == 2
    assert stats["failed"] == 1
    assert db.committed

    # Verify cfg3 was re-encrypted with current key
    decrypted = ConfigCrypto.decrypt_value(cfg3.config_value, current_key)
    assert decrypted == {"api_key": "old"}


@pytest.mark.asyncio
async def test_validate_recovery_key():
    """Test validation of recovery key."""
    from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto

    from app.services.config.encryption import get_encryption_service
    from app.services.config.migration import validate_recovery_key

    class MockConfig:
        def __init__(self, key, value):
            self.id = 1
            self.config_key = key
            self.config_value = value
            self.version = 1

    class MockResult:
        def __init__(self, configs):
            self._configs = configs

        def scalars(self):
            class Scalars:
                def all(self_inner):
                    return self._configs

            return Scalars()

    class MockSession:
        def __init__(self, configs):
            self._configs = configs
            self.committed = False

        async def execute(self, query):
            return MockResult(self._configs)

        async def commit(self):
            self.committed = True

    svc = get_encryption_service()
    current_key = svc._key
    assert current_key is not None

    old_key = os.urandom(32)

    # Config 1: Plaintext (should be skipped)
    cfg1 = MockConfig("providers", {"api_key": "plain"})
    # Config 2: Encrypted with current key (should be skipped)
    cfg2_val = ConfigCrypto.encrypt_value({"api_key": "current"}, current_key)
    cfg2 = MockConfig("retrieval", cfg2_val)
    # Config 3: Encrypted with old key (should be recoverable)
    cfg3_val = ConfigCrypto.encrypt_value({"api_key": "old"}, old_key)
    cfg3 = MockConfig("searchServices", cfg3_val)
    # Config 4: Encrypted with some other key (should fail)
    cfg4_val = ConfigCrypto.encrypt_value({"api_key": "other"}, os.urandom(32))
    cfg4 = MockConfig("mcpServers", cfg4_val)

    db = MockSession([cfg1, cfg2, cfg3, cfg4])

    stats = await validate_recovery_key(db, old_key)

    assert stats["recoverable"] == 1
    assert stats["skipped"] == 2
    assert stats["failed"] == 1
    assert not db.committed
