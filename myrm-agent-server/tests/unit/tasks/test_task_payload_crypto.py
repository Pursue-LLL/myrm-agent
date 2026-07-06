"""Tests for task payload secret sealing at rest."""

from __future__ import annotations

import pytest

from app.tasks.task_payload_crypto import (
    API_KEY_ENC_FIELD,
    API_KEY_FIELD,
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


def test_open_task_payload_supports_legacy_plaintext() -> None:
    payload = {API_KEY_FIELD: "sk-legacy"}
    opened = open_task_payload_secrets(payload)
    assert opened[API_KEY_FIELD] == "sk-legacy"


def test_seal_noop_without_api_key() -> None:
    payload = {"model": "dall-e-3", "prompt": "x"}
    assert seal_task_payload_secrets(payload) == payload
