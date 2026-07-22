"""Encrypt sensitive fields in async task payloads stored in local tasks.db.

[INPUT]
- app.services.config.encryption::get_encryption_service (POS: local/sandbox encryption key)
- myrm_agent_harness.utils.crypto::ConfigCrypto (POS: AES-GCM encrypt/decrypt)

[OUTPUT]
- seal_task_payload_secrets(): encrypt api_key and gateway auth_token before persist
- open_task_payload_secrets(): restore secrets for worker resolver (sealed fields only)

[POS]
Server-side at-rest protection for harness task queue payloads; harness stays crypto-agnostic.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

logger = logging.getLogger(__name__)

API_KEY_FIELD = "api_key"
API_KEY_ENC_FIELD = "api_key_enc"
GATEWAY_CONFIG_FIELD = "gateway_config"
FALLBACK_CONFIGS_FIELD = "fallback_configs"
AUTH_TOKEN_FIELD = "auth_token"
AUTH_TOKEN_ENC_FIELD = "auth_token_enc"


def _encryption_raw_key() -> bytes | None:
    from app.services.config.encryption import get_encryption_service

    service = get_encryption_service()
    if not service.has_key or service.raw_key is None:
        return None
    return service.raw_key


def _encrypt_secret(value: str, raw_key: bytes) -> str:
    return ConfigCrypto.encrypt_value({"value": value.strip()}, raw_key)


def _decrypt_secret(ciphertext: str, raw_key: bytes) -> str | None:
    try:
        decrypted = ConfigCrypto.decrypt_value(ciphertext.strip(), raw_key)
    except DecryptionError:
        logger.warning("Failed to decrypt task payload secret", exc_info=True)
        return None
    plain = decrypted.get("value")
    if not isinstance(plain, str) or not plain.strip():
        return None
    return plain.strip()


def _seal_gateway_config(
    gateway_config: dict[str, object],
    raw_key: bytes,
) -> dict[str, object]:
    auth_token_raw = gateway_config.get(AUTH_TOKEN_FIELD)
    if not isinstance(auth_token_raw, str) or not auth_token_raw.strip():
        return gateway_config

    sealed_gateway = dict(gateway_config)
    sealed_gateway[AUTH_TOKEN_ENC_FIELD] = _encrypt_secret(auth_token_raw, raw_key)
    del sealed_gateway[AUTH_TOKEN_FIELD]
    return sealed_gateway


def _open_gateway_config(
    gateway_config: dict[str, object],
    raw_key: bytes,
) -> dict[str, object]:
    enc = gateway_config.get(AUTH_TOKEN_ENC_FIELD)
    if not isinstance(enc, str) or not enc.strip():
        return gateway_config

    plain = _decrypt_secret(enc, raw_key)
    if plain is None:
        failed_gateway = dict(gateway_config)
        failed_gateway.pop(AUTH_TOKEN_ENC_FIELD, None)
        return failed_gateway

    opened_gateway = dict(gateway_config)
    opened_gateway[AUTH_TOKEN_FIELD] = plain
    del opened_gateway[AUTH_TOKEN_ENC_FIELD]
    return opened_gateway


def _strip_plaintext_secrets_in_tree(config: dict[str, object]) -> dict[str, object]:
    stripped = dict(config)
    if API_KEY_FIELD in stripped:
        del stripped[API_KEY_FIELD]

    gateway_raw = stripped.get(GATEWAY_CONFIG_FIELD)
    if isinstance(gateway_raw, dict) and AUTH_TOKEN_FIELD in gateway_raw:
        gateway_copy = dict(gateway_raw)
        del gateway_copy[AUTH_TOKEN_FIELD]
        stripped[GATEWAY_CONFIG_FIELD] = gateway_copy

    fallback_raw = stripped.get(FALLBACK_CONFIGS_FIELD)
    if isinstance(fallback_raw, list):
        fallback_sanitized: list[object] = []
        for item in fallback_raw:
            if isinstance(item, dict):
                fallback_sanitized.append(_strip_plaintext_secrets_in_tree(item))
            else:
                fallback_sanitized.append(item)
        stripped[FALLBACK_CONFIGS_FIELD] = fallback_sanitized

    return stripped


def _seal_secret_tree(config: dict[str, object], raw_key: bytes) -> dict[str, object]:
    sealed = dict(config)

    api_key_raw = sealed.get(API_KEY_FIELD)
    if isinstance(api_key_raw, str) and api_key_raw.strip():
        sealed[API_KEY_ENC_FIELD] = _encrypt_secret(api_key_raw, raw_key)
        del sealed[API_KEY_FIELD]

    gateway_raw = sealed.get(GATEWAY_CONFIG_FIELD)
    if isinstance(gateway_raw, dict):
        sealed[GATEWAY_CONFIG_FIELD] = _seal_gateway_config(gateway_raw, raw_key)

    fallback_raw = sealed.get(FALLBACK_CONFIGS_FIELD)
    if isinstance(fallback_raw, list):
        sealed_fallbacks: list[object] = []
        for item in fallback_raw:
            if isinstance(item, dict):
                sealed_fallbacks.append(_seal_secret_tree(item, raw_key))
            else:
                sealed_fallbacks.append(item)
        sealed[FALLBACK_CONFIGS_FIELD] = sealed_fallbacks

    return sealed


def _open_secret_tree(config: dict[str, object], raw_key: bytes) -> dict[str, object]:
    opened = _strip_plaintext_secrets_in_tree(config)

    enc = config.get(API_KEY_ENC_FIELD)
    if isinstance(enc, str) and enc.strip():
        plain = _decrypt_secret(enc, raw_key)
        if plain is not None:
            opened[API_KEY_FIELD] = plain

    gateway_raw = config.get(GATEWAY_CONFIG_FIELD)
    if isinstance(gateway_raw, dict):
        gateway_sanitized = dict(gateway_raw)
        gateway_sanitized.pop(AUTH_TOKEN_FIELD, None)
        opened[GATEWAY_CONFIG_FIELD] = _open_gateway_config(gateway_sanitized, raw_key)

    fallback_raw = config.get(FALLBACK_CONFIGS_FIELD)
    if isinstance(fallback_raw, list):
        opened_fallbacks: list[object] = []
        for item in fallback_raw:
            if isinstance(item, dict):
                opened_fallbacks.append(_open_secret_tree(item, raw_key))
            else:
                opened_fallbacks.append(item)
        opened[FALLBACK_CONFIGS_FIELD] = opened_fallbacks

    return opened


def _has_plaintext_secrets(config: dict[str, object]) -> bool:
    api_key_raw = config.get(API_KEY_FIELD)
    if isinstance(api_key_raw, str) and api_key_raw.strip():
        return True

    gateway_raw = config.get(GATEWAY_CONFIG_FIELD)
    if (
        isinstance(gateway_raw, dict)
        and isinstance(gateway_raw.get(AUTH_TOKEN_FIELD), str)
        and bool(str(gateway_raw.get(AUTH_TOKEN_FIELD)).strip())
    ):
        return True

    fallback_raw = config.get(FALLBACK_CONFIGS_FIELD)
    if isinstance(fallback_raw, list):
        return any(_has_plaintext_secrets(item) for item in fallback_raw if isinstance(item, dict))

    return False


def _has_encrypted_secrets(config: dict[str, object]) -> bool:
    enc_api_key = config.get(API_KEY_ENC_FIELD)
    if isinstance(enc_api_key, str) and enc_api_key.strip():
        return True

    gateway_raw = config.get(GATEWAY_CONFIG_FIELD)
    if (
        isinstance(gateway_raw, dict)
        and isinstance(gateway_raw.get(AUTH_TOKEN_ENC_FIELD), str)
        and bool(str(gateway_raw.get(AUTH_TOKEN_ENC_FIELD)).strip())
    ):
        return True

    fallback_raw = config.get(FALLBACK_CONFIGS_FIELD)
    if isinstance(fallback_raw, list):
        return any(_has_encrypted_secrets(item) for item in fallback_raw if isinstance(item, dict))

    return False


def _strip_unsealed_secrets(payload: dict[str, object]) -> dict[str, object]:
    """Remove plaintext secrets when encryption key is unavailable (fail closed at rest)."""
    return _strip_plaintext_secrets_in_tree(payload)


def seal_task_payload_secrets(payload: dict[str, object]) -> dict[str, object]:
    """Return a payload copy with sensitive fields encrypted before tasks.db persist."""
    raw_key = _encryption_raw_key()
    if raw_key is None:
        if _has_plaintext_secrets(payload):
            logger.warning("Task payload secrets stripped: encryption key unavailable")
            return _strip_unsealed_secrets(payload)
        return payload

    return _seal_secret_tree(payload, raw_key)


def open_task_payload_secrets(payload: dict[str, object]) -> dict[str, object]:
    """Return a payload copy with secrets restored from sealed fields only."""
    opened = _strip_unsealed_secrets(payload)

    raw_key = _encryption_raw_key()
    if raw_key is None:
        if _has_encrypted_secrets(payload):
            logger.warning("Cannot decrypt task payload secrets: encryption key unavailable")
        return opened

    return _open_secret_tree(payload, raw_key)


__all__ = [
    "API_KEY_ENC_FIELD",
    "API_KEY_FIELD",
    "AUTH_TOKEN_ENC_FIELD",
    "AUTH_TOKEN_FIELD",
    "FALLBACK_CONFIGS_FIELD",
    "GATEWAY_CONFIG_FIELD",
    "open_task_payload_secrets",
    "seal_task_payload_secrets",
]
