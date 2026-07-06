"""Encrypt sensitive fields in async task payloads stored in local tasks.db.

[INPUT]
- app.services.config.encryption::get_encryption_service (POS: local/sandbox encryption key)
- myrm_agent_harness.utils.crypto::ConfigCrypto (POS: AES-GCM encrypt/decrypt)

[OUTPUT]
- seal_task_payload_secrets(): move plaintext api_key → api_key_enc ciphertext
- open_task_payload_secrets(): restore api_key for worker resolver (legacy plaintext supported)

[POS]
Server-side at-rest protection for harness task queue payloads; harness stays crypto-agnostic.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

logger = logging.getLogger(__name__)

API_KEY_FIELD = "api_key"
API_KEY_ENC_FIELD = "api_key_enc"


def seal_task_payload_secrets(payload: dict[str, object]) -> dict[str, object]:
    """Return a payload copy with api_key encrypted at rest when a key is available."""
    api_key_raw = payload.get(API_KEY_FIELD)
    if not isinstance(api_key_raw, str) or not api_key_raw.strip():
        return payload

    from app.services.config.encryption import get_encryption_service

    service = get_encryption_service()
    if not service.has_key or service.raw_key is None:
        logger.warning("Task payload api_key left plaintext: encryption key unavailable")
        return payload

    sealed = dict(payload)
    sealed[API_KEY_ENC_FIELD] = ConfigCrypto.encrypt_value({"value": api_key_raw.strip()}, service.raw_key)
    del sealed[API_KEY_FIELD]
    return sealed


def open_task_payload_secrets(payload: dict[str, object]) -> dict[str, object]:
    """Return a payload copy with api_key restored from api_key_enc when sealed."""
    if isinstance(payload.get(API_KEY_FIELD), str):
        return payload

    enc = payload.get(API_KEY_ENC_FIELD)
    if not isinstance(enc, str) or not enc.strip():
        return payload

    from app.services.config.encryption import get_encryption_service

    service = get_encryption_service()
    if not service.has_key or service.raw_key is None:
        logger.warning("Cannot decrypt task payload api_key_enc: encryption key unavailable")
        return payload

    try:
        decrypted = ConfigCrypto.decrypt_value(enc.strip(), service.raw_key)
    except DecryptionError:
        logger.warning("Failed to decrypt task payload api_key_enc", exc_info=True)
        return payload

    value = decrypted.get("value")
    if not isinstance(value, str) or not value.strip():
        return payload

    opened = dict(payload)
    opened[API_KEY_FIELD] = value.strip()
    return opened


__all__ = [
    "API_KEY_ENC_FIELD",
    "API_KEY_FIELD",
    "open_task_payload_secrets",
    "seal_task_payload_secrets",
]
