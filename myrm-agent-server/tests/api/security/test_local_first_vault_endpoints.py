"""API endpoint tests for Local-First Zero-Leak Vault and Zero-Knowledge E2EE Sharing Gateway."""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.local_first_vault_router import (
    router as local_first_vault_router,
)
from app.services.security.local_first_vault_service import (
    LocalFirstVaultService,
    get_local_first_vault_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = LocalFirstVaultService()
    app = FastAPI()
    app.include_router(local_first_vault_router, prefix="/api/v1/security")
    app.dependency_overrides[get_local_first_vault_service] = lambda: test_service
    return TestClient(app)


def test_dlp_sanitize_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/local-first-vault/dlp/sanitize",
        json={
            "content": "Staging server 172.20.1.4 and key sk_live_1234567890abcdef12345678. Price: $15,000.00.",
            "enable_price_redaction": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_redactions"] == 3
    assert "172.20.1.4" not in data["sanitized_content"]
    assert "sk_live_" not in data["sanitized_content"]
    assert "$15,000.00" not in data["sanitized_content"]
    assert "[INTERNAL_IP_MASKED]" in data["sanitized_content"]
    assert "[SECRET_TOKEN_REDACTED]" in data["sanitized_content"]
    assert "[CONFIDENTIAL_PRICE_REDACTED]" in data["sanitized_content"]


def test_artifacts_lifecycle_endpoints(client: TestClient) -> None:
    # 1. Register local artifact
    resp_reg = client.post(
        "/api/v1/security/local-first-vault/artifacts",
        json={
            "artifact_id": "art_api_doc_01",
            "title": "Confidential Security Whitepaper",
            "local_path": "/var/data/whitepaper.pdf",
            "content": "Confidential internal specs",
            "storage_mode": "local_first_disk",
        },
    )
    assert resp_reg.status_code == 201
    item = resp_reg.json()
    assert item["artifact_id"] == "art_api_doc_01"
    assert item["is_cloud_synced"] is False
    assert item["storage_mode"] == "local_first_disk"

    # 2. Get artifact by ID
    resp_get = client.get("/api/v1/security/local-first-vault/artifacts/art_api_doc_01")
    assert resp_get.status_code == 200
    assert resp_get.json()["artifact_id"] == "art_api_doc_01"

    # 3. List artifacts
    resp_list = client.get("/api/v1/security/local-first-vault/artifacts")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

    # 4. Non-existent artifact returns 404
    resp_404 = client.get("/api/v1/security/local-first-vault/artifacts/unknown_art_id")
    assert resp_404.status_code == 404


def test_e2ee_share_and_decrypt_endpoints(client: TestClient) -> None:
    # 1. Create E2EE share
    resp_share = client.post(
        "/api/v1/security/local-first-vault/e2ee/share",
        json={
            "artifact_id": "art_api_deck_02",
            "plaintext_content": "Sensitive project on host 10.10.1.88 with cost $80,000.00.",
            "ttl_seconds": 3600,
            "enable_dlp_sanitization": True,
        },
    )
    assert resp_share.status_code == 201
    share_data = resp_share.json()
    share_id = share_data["share_id"]
    client_key_b64 = share_data["client_key_b64"]
    assert share_data["dlp_audit_passed"] is True
    assert "#share_id=" in share_data["share_url_fragment"]

    # 2. Decrypt with valid key
    resp_decrypt = client.post(
        f"/api/v1/security/local-first-vault/e2ee/decrypt/{share_id}",
        json={"client_key_b64": client_key_b64},
    )
    assert resp_decrypt.status_code == 200
    dec_data = resp_decrypt.json()
    assert dec_data["share_id"] == share_id
    assert "10.10.1.88" not in dec_data["decrypted_content"]
    assert "[INTERNAL_IP_MASKED]" in dec_data["decrypted_content"]
    assert "[CONFIDENTIAL_PRICE_REDACTED]" in dec_data["decrypted_content"]

    # 3. Decrypt with invalid key returns 400
    fake_key_b64 = base64.b64encode(b"0" * 32).decode("utf-8")
    resp_bad_key = client.post(
        f"/api/v1/security/local-first-vault/e2ee/decrypt/{share_id}",
        json={"client_key_b64": fake_key_b64},
    )
    assert resp_bad_key.status_code == 400

    # 4. Decrypt non-existent share returns 404
    resp_not_found = client.post(
        "/api/v1/security/local-first-vault/e2ee/decrypt/non_existent_share",
        json={"client_key_b64": client_key_b64},
    )
    assert resp_not_found.status_code == 404
