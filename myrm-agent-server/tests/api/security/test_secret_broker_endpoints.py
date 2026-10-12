"""Integration tests for Secret Broker and Credential Isolation API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.secret_broker_router import router as secret_broker_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting secret_broker_router."""
    test_app = FastAPI(title="Secret Broker Test App")
    test_app.include_router(secret_broker_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_ingest_and_list_handles(client: TestClient) -> None:
    # 1. Ingest secret
    resp = client.post(
        "/api/v1/security/secret-broker/ingest",
        json={
            "secret_name": "GITHUB_PAT",
            "secret_value": "ghp_secure_personal_token_999",
            "allowed_host": "api.github.com",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "handle" in data
    handle = data["handle"]
    assert handle["secret_name"] == "GITHUB_PAT"
    assert handle["allowed_host"] == "api.github.com"
    handle_id = handle["handle_id"]

    # 2. List handles
    list_resp = client.get("/api/v1/security/secret-broker/handles")
    assert list_resp.status_code == 200
    handles = list_resp.json()
    assert any(h["handle_id"] == handle_id for h in handles)


def test_resolve_egress_matching_and_mismatch(client: TestClient) -> None:
    # Ingest secret
    ingest_resp = client.post(
        "/api/v1/security/secret-broker/ingest",
        json={
            "secret_name": "SENDGRID_KEY",
            "secret_value": "SG.test_key_12345",
            "allowed_host": "api.sendgrid.com",
        },
    )
    assert ingest_resp.status_code == 201
    handle = ingest_resp.json()["handle"]
    placeholder = handle["placeholder"]

    # Authorized host resolution
    resolve_resp = client.post(
        "/api/v1/security/secret-broker/resolve-egress",
        json={
            "content": f"Bearer {placeholder}",
            "target_host": "api.sendgrid.com",
        },
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["authorized"] is True
    assert res_data["replacements_count"] == 1
    assert res_data["resolved_content"] == "Bearer SG.test_key_12345"

    # Mismatched host resolution blocked (403)
    blocked_resp = client.post(
        "/api/v1/security/secret-broker/resolve-egress",
        json={
            "content": f"Bearer {placeholder}",
            "target_host": "malicious.egress.org",
        },
    )
    assert blocked_resp.status_code == 403


def test_atomic_grant_lifecycle_endpoints(client: TestClient) -> None:
    # 1. Create grant
    payload = {"account": "corp-01", "action": "transfer", "amount": 1000}
    create_resp = client.post(
        "/api/v1/security/secret-broker/grants/create",
        json={
            "operation_name": "wire_transfer",
            "payload": payload,
            "ttl_seconds": 120.0,
        },
    )
    assert create_resp.status_code == 201
    grant = create_resp.json()
    grant_id = grant["grant_id"]
    assert grant["status"] == "pending"

    # 2. Approve grant
    approve_resp = client.post(f"/api/v1/security/secret-broker/grants/{grant_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "granted"

    # 3. Consume grant
    consume_resp = client.post(
        f"/api/v1/security/secret-broker/grants/{grant_id}/consume",
        json={"operation_name": "wire_transfer", "payload": payload},
    )
    assert consume_resp.status_code == 200
    assert consume_resp.json()["success"] is True

    # 4. Reject another grant
    create_resp2 = client.post(
        "/api/v1/security/secret-broker/grants/create",
        json={
            "operation_name": "wipe_storage",
            "payload": {"disk": "/dev/sda"},
        },
    )
    grant_id2 = create_resp2.json()["grant_id"]

    reject_resp = client.post(
        f"/api/v1/security/secret-broker/grants/{grant_id2}/reject",
        json={"reason": "Forbidden by administrator policy"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "revoked"

    # Consuming revoked grant returns 403
    consume_revoked = client.post(
        f"/api/v1/security/secret-broker/grants/{grant_id2}/consume",
        json={"operation_name": "wipe_storage", "payload": {"disk": "/dev/sda"}},
    )
    assert consume_revoked.status_code == 403
