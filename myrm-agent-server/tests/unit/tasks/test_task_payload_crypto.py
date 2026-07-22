"""Tests for task payload secret sealing at rest."""

from __future__ import annotations

import pytest

from app.tasks.task_payload_crypto import (
    API_KEY_ENC_FIELD,
    API_KEY_FIELD,
    AUTH_TOKEN_ENC_FIELD,
    AUTH_TOKEN_FIELD,
    FALLBACK_CONFIGS_FIELD,
    GATEWAY_CONFIG_FIELD,
    open_task_payload_secrets,
    seal_task_payload_secrets,
)


@pytest.fixture(autouse=True)
def _reset_encryption_singleton() -> None:
    import os

    import app.services.config.encryption as enc_mod

    original_deploy = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    enc_mod._encryption_service = None
    yield
    enc_mod._encryption_service = None
    if original_deploy is None:
        os.environ.pop("DEPLOY_MODE", None)
    else:
        os.environ["DEPLOY_MODE"] = original_deploy


def test_seal_task_payload_moves_api_key_to_encrypted_field() -> None:
    payload = {"model": "flux-pro", API_KEY_FIELD: "sk-seal-me", "prompt": "x"}
    sealed = seal_task_payload_secrets(payload)

    assert API_KEY_FIELD not in sealed
    assert isinstance(sealed.get(API_KEY_ENC_FIELD), str)
    assert sealed[API_KEY_ENC_FIELD] != "sk-seal-me"

    opened = open_task_payload_secrets(sealed)
    assert opened[API_KEY_FIELD] == "sk-seal-me"


def test_open_task_payload_ignores_legacy_plaintext_api_key() -> None:
    payload = {API_KEY_FIELD: "sk-legacy"}
    opened = open_task_payload_secrets(payload)
    assert API_KEY_FIELD not in opened


def test_seal_noop_without_api_key() -> None:
    payload = {"model": "dall-e-3", "prompt": "x"}
    assert seal_task_payload_secrets(payload) == payload


def test_seal_task_payload_encrypts_gateway_auth_token() -> None:
    payload = {
        "model": "flux-pro",
        GATEWAY_CONFIG_FIELD: {
            "use_gateway": True,
            "gateway_url": "https://gateway.example/tool-relay",
            AUTH_TOKEN_FIELD: "vk-gateway-token",
        },
    }
    sealed = seal_task_payload_secrets(payload)

    gateway = sealed.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(gateway, dict)
    assert AUTH_TOKEN_FIELD not in gateway
    assert isinstance(gateway.get(AUTH_TOKEN_ENC_FIELD), str)

    opened = open_task_payload_secrets(sealed)
    opened_gateway = opened.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(opened_gateway, dict)
    assert opened_gateway[AUTH_TOKEN_FIELD] == "vk-gateway-token"
    assert AUTH_TOKEN_ENC_FIELD not in opened_gateway


def test_seal_task_payload_encrypts_api_key_and_gateway_token_together() -> None:
    payload = {
        API_KEY_FIELD: "sk-both",
        GATEWAY_CONFIG_FIELD: {
            "use_gateway": True,
            "gateway_url": "https://gateway.example/tool-relay",
            AUTH_TOKEN_FIELD: "vk-both",
        },
    }
    sealed = seal_task_payload_secrets(payload)

    assert API_KEY_FIELD not in sealed
    gateway = sealed.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(gateway, dict)
    assert AUTH_TOKEN_FIELD not in gateway

    opened = open_task_payload_secrets(sealed)
    assert opened[API_KEY_FIELD] == "sk-both"
    opened_gateway = opened.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(opened_gateway, dict)
    assert opened_gateway[AUTH_TOKEN_FIELD] == "vk-both"


def test_seal_strips_secrets_when_encryption_key_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.config.encryption as enc_mod

    class _NoKeyService:
        has_key = False
        raw_key = None

    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: _NoKeyService())

    payload = {
        API_KEY_FIELD: "sk-strip",
        GATEWAY_CONFIG_FIELD: {
            "use_gateway": True,
            "gateway_url": "https://gateway.example/tool-relay",
            AUTH_TOKEN_FIELD: "vk-strip",
        },
    }
    sealed = seal_task_payload_secrets(payload)

    assert API_KEY_FIELD not in sealed
    gateway = sealed.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(gateway, dict)
    assert AUTH_TOKEN_FIELD not in gateway


def test_open_without_encryption_key_leaves_sealed_fields_and_strips_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.config.encryption as enc_mod

    class _NoKeyService:
        has_key = False
        raw_key = None

    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: _NoKeyService())

    sealed = {API_KEY_ENC_FIELD: "cipher-text", API_KEY_FIELD: "should-drop"}
    opened = open_task_payload_secrets(sealed)

    assert API_KEY_FIELD not in opened
    assert opened[API_KEY_ENC_FIELD] == "cipher-text"


def test_open_gateway_decrypt_failure_strips_auth_token_enc(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.utils.crypto import DecryptionError

    import app.services.config.encryption as enc_mod

    class _BrokenDecryptService:
        has_key = True
        raw_key = b"0" * 32

    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: _BrokenDecryptService())

    def _raise(_ciphertext: str, _raw_key: bytes) -> dict[str, object]:
        raise DecryptionError("bad cipher")

    monkeypatch.setattr(
        "app.tasks.task_payload_crypto.ConfigCrypto.decrypt_value",
        _raise,
    )

    sealed = {
        GATEWAY_CONFIG_FIELD: {
            "use_gateway": True,
            AUTH_TOKEN_ENC_FIELD: "bad-cipher",
        },
    }
    opened = open_task_payload_secrets(sealed)
    gateway = opened.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(gateway, dict)
    assert AUTH_TOKEN_FIELD not in gateway
    assert AUTH_TOKEN_ENC_FIELD not in gateway


def test_seal_gateway_without_auth_token_is_noop() -> None:
    payload = {
        GATEWAY_CONFIG_FIELD: {
            "use_gateway": True,
            "gateway_url": "https://gateway.example/tool-relay",
        },
    }
    sealed = seal_task_payload_secrets(payload)
    gateway = sealed.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(gateway, dict)
    assert AUTH_TOKEN_ENC_FIELD not in gateway


def test_seal_and_open_nested_fallback_secrets() -> None:
    payload = {
        "model": "sora",
        FALLBACK_CONFIGS_FIELD: [
            {
                "provider": "openai",
                "model": "sora",
                API_KEY_FIELD: "sk-fallback",
                GATEWAY_CONFIG_FIELD: {
                    "use_gateway": True,
                    AUTH_TOKEN_FIELD: "vk-fallback",
                },
            }
        ],
    }

    sealed = seal_task_payload_secrets(payload)
    fallback = sealed.get(FALLBACK_CONFIGS_FIELD)
    assert isinstance(fallback, list)
    fallback_item = fallback[0]
    assert isinstance(fallback_item, dict)
    assert API_KEY_FIELD not in fallback_item
    assert isinstance(fallback_item.get(API_KEY_ENC_FIELD), str)
    fallback_gateway = fallback_item.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(fallback_gateway, dict)
    assert AUTH_TOKEN_FIELD not in fallback_gateway
    assert isinstance(fallback_gateway.get(AUTH_TOKEN_ENC_FIELD), str)

    opened = open_task_payload_secrets(sealed)
    opened_fallback = opened.get(FALLBACK_CONFIGS_FIELD)
    assert isinstance(opened_fallback, list)
    opened_item = opened_fallback[0]
    assert isinstance(opened_item, dict)
    assert opened_item[API_KEY_FIELD] == "sk-fallback"
    opened_gateway = opened_item.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(opened_gateway, dict)
    assert opened_gateway[AUTH_TOKEN_FIELD] == "vk-fallback"


def test_seal_strips_nested_fallback_plaintext_without_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.config.encryption as enc_mod

    class _NoKeyService:
        has_key = False
        raw_key = None

    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: _NoKeyService())

    payload = {
        FALLBACK_CONFIGS_FIELD: [
            {
                API_KEY_FIELD: "sk-fallback",
                GATEWAY_CONFIG_FIELD: {
                    AUTH_TOKEN_FIELD: "vk-fallback",
                },
            }
        ]
    }
    sealed = seal_task_payload_secrets(payload)
    fallback = sealed.get(FALLBACK_CONFIGS_FIELD)
    assert isinstance(fallback, list)
    fallback_item = fallback[0]
    assert isinstance(fallback_item, dict)
    assert API_KEY_FIELD not in fallback_item
    fallback_gateway = fallback_item.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(fallback_gateway, dict)
    assert AUTH_TOKEN_FIELD not in fallback_gateway


def test_open_without_key_preserves_nested_ciphertext_and_strips_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.config.encryption as enc_mod

    class _NoKeyService:
        has_key = False
        raw_key = None

    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: _NoKeyService())

    payload = {
        FALLBACK_CONFIGS_FIELD: [
            {
                API_KEY_FIELD: "sk-plain",
                API_KEY_ENC_FIELD: "cipher-key",
                GATEWAY_CONFIG_FIELD: {
                    AUTH_TOKEN_FIELD: "vk-plain",
                    AUTH_TOKEN_ENC_FIELD: "cipher-token",
                },
            }
        ]
    }
    opened = open_task_payload_secrets(payload)
    fallback = opened.get(FALLBACK_CONFIGS_FIELD)
    assert isinstance(fallback, list)
    fallback_item = fallback[0]
    assert isinstance(fallback_item, dict)
    assert API_KEY_FIELD not in fallback_item
    assert fallback_item[API_KEY_ENC_FIELD] == "cipher-key"
    fallback_gateway = fallback_item.get(GATEWAY_CONFIG_FIELD)
    assert isinstance(fallback_gateway, dict)
    assert AUTH_TOKEN_FIELD not in fallback_gateway
    assert fallback_gateway[AUTH_TOKEN_ENC_FIELD] == "cipher-token"

