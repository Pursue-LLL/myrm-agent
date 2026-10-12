"""
[POS] tests/api/security/test_keychain_rest_encryption_endpoints.py
[INPUT] fastapi, fastapi.testclient, myrm_agent_harness, app.api.security.keychain_rest_encryption_router, app.services.security.keychain_rest_encryption_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for OS Keychain & Transparent Rest Encryption Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.keychain_rest_encryption import (
    KeychainBackendType,
    KeychainRestEncryptionSuite,
)

from app.api.security.keychain_rest_encryption_router import router as keychain_router
from app.services.security.keychain_rest_encryption_service import (
    KeychainRestEncryptionService,
    get_keychain_rest_encryption_service,
)


@pytest.fixture
def client() -> TestClient:
    suite = KeychainRestEncryptionSuite(
        service_name="test.myrm.api.service",
        account_name="test_api_account",
        force_backend=KeychainBackendType.FALLBACK_EPHEMERAL,
    )
    test_service = KeychainRestEncryptionService(suite=suite)

    app = FastAPI()
    app.include_router(keychain_router)
    app.dependency_overrides[get_keychain_rest_encryption_service] = lambda: test_service
    return TestClient(app)


def test_status_and_self_test_endpoints(client: TestClient) -> None:
    """Validate GET /keychain-rest-encryption/status and POST /self-test."""
    # 1. Status
    res = client.get("/keychain-rest-encryption/status")
    assert res.status_code == 200
    data = res.json()
    assert data["backend_type"] == "FALLBACK_EPHEMERAL"
    assert not data["is_hardware_backed"]
    assert "HEALTH_RECORDS" in data["active_domains"]

    # 2. Self-test
    self_test_res = client.post("/keychain-rest-encryption/self-test")
    assert self_test_res.status_code == 200
    st_data = self_test_res.json()
    assert st_data["passed"] is True
    assert st_data["envelope_id"].startswith("env-")


def test_encrypt_and_decrypt_endpoints(client: TestClient) -> None:
    """Validate POST /encrypt and POST /decrypt."""
    raw_text = "MedicalDiagnosticTestNote:Patient123"

    # Encrypt
    enc_res = client.post(
        "/keychain-rest-encryption/encrypt",
        json={
            "text": raw_text,
            "domain": "HEALTH_RECORDS",
        },
    )
    assert enc_res.status_code == 200
    env_data = enc_res.json()["envelope"]
    assert env_data["domain"] == "HEALTH_RECORDS"
    assert env_data["ciphertext_hex"] != ""

    # Decrypt
    dec_res = client.post(
        "/keychain-rest-encryption/decrypt",
        json={"envelope": env_data},
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["plaintext"] == raw_text

    # Decrypt with tampered tag
    tampered_env = dict(env_data)
    tampered_env["tag_hex"] = "00" * 16
    fail_res = client.post(
        "/keychain-rest-encryption/decrypt",
        json={"envelope": tampered_env},
    )
    assert fail_res.status_code == 400
    assert "Decryption failed" in fail_res.json()["detail"]


def test_file_encrypt_decrypt_endpoints(client: TestClient, tmp_path: Path) -> None:
    """Validate POST /encrypt-file and POST /decrypt-file."""
    src = tmp_path / "private_journal.md"
    enc = tmp_path / "private_journal.md.enc"
    dec = tmp_path / "private_journal_restored.md"

    journal_text = "## Private Thoughts\nSecret entry for 2026-10-06."
    src.write_text(journal_text, encoding="utf-8")

    # Encrypt file
    enc_res = client.post(
        "/keychain-rest-encryption/encrypt-file",
        json={
            "source_path": str(src),
            "dest_path": str(enc),
            "domain": "PERSONAL_JOURNAL",
        },
    )
    assert enc_res.status_code == 200
    assert enc.exists()

    # Decrypt file
    dec_res = client.post(
        "/keychain-rest-encryption/decrypt-file",
        json={
            "source_path": str(enc),
            "dest_path": str(dec),
        },
    )
    assert dec_res.status_code == 200
    assert dec.exists()
    assert dec.read_text(encoding="utf-8") == journal_text


def test_purge_and_metrics_endpoints(client: TestClient) -> None:
    """Validate POST /purge and GET /metrics."""
    # Run encryption first
    client.post(
        "/keychain-rest-encryption/encrypt",
        json={"text": "sample", "domain": "GENERAL_REST"},
    )

    # Purge
    purge_res = client.post(
        "/keychain-rest-encryption/purge",
        json={"scope": "KEYCHAIN_AND_MEMORY"},
    )
    assert purge_res.status_code == 200
    p_data = purge_res.json()
    assert p_data["keys_zeroized"] >= 1
    assert p_data["keychain_deleted"] is True

    # Metrics
    m_res = client.get("/keychain-rest-encryption/metrics")
    assert m_res.status_code == 200
    m_data = m_res.json()
    assert m_data["encryptions_total"] >= 1
    assert m_data["purges_total"] >= 1
