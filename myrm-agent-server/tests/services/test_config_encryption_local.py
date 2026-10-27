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
    from app.services.config.encryption import (
        get_encryption_service,
        is_sensitive_config,
    )

    svc = get_encryption_service()

    assert svc._is_local is True
    assert svc._is_sandbox is False
    assert svc._key is not None
    assert len(svc._key) == 32

    assert svc.should_encrypt("providers") is True
    assert svc.should_encrypt("chatSettings") is False

    assert is_sensitive_config("providers") is True
    assert is_sensitive_config("retrieval") is True
    assert is_sensitive_config("mcpServers") is True
    assert is_sensitive_config("orgMcpServers") is True
    assert is_sensitive_config("mcpOAuthTokens") is True
    assert is_sensitive_config("oauthCredentials") is True
    assert is_sensitive_config("feishu_a1b2c3Credentials") is True
    assert is_sensitive_config("wechat_x9y8z7Credentials") is True
    assert is_sensitive_config("egress_proxy") is True
    assert is_sensitive_config("egressProxy") is True
    assert is_sensitive_config("llm_proxy") is True
    assert is_sensitive_config("llmProxy") is True
    assert is_sensitive_config("backupSync") is True
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
