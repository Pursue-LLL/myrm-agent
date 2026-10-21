"""API endpoint tests for Inbound Zero-Trust Quarantine & Redaction in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.inbound_quarantine import (
    InboundQuarantineGate,
)

from app.api.security.inbound_quarantine_router import (
    router as inbound_quarantine_router,
)
from app.services.security.inbound_quarantine_service import (
    InboundQuarantineService,
    get_inbound_quarantine_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    gate = InboundQuarantineGate()
    service = InboundQuarantineService(gate=gate)

    app.dependency_overrides[get_inbound_quarantine_service] = lambda: service
    app.include_router(inbound_quarantine_router, prefix="/api/v1/security")
    return TestClient(app)


def test_inspect_clean_message_api(client: TestClient) -> None:
    payload = {
        "content": "Meeting scheduled tomorrow morning at 10 AM.",
        "channel_type": "email",
        "sender": "lead@company.com",
        "recipient": "agent@company.com",
    }
    resp = client.post("/api/v1/security/inbound-quarantine/inspect", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_quarantined"] is False
    assert len(data["detected_risks"]) == 0
    assert data["safe_content"] == payload["content"]
    assert data["quarantine_id"] is None


def test_inspect_sensitive_message_and_release_flow_api(
    client: TestClient,
) -> None:
    secret_body = (
        "Security Alert: Your one-time verification code is 782194. "
        "Valid for 10 minutes."
    )
    payload = {
        "content": secret_body,
        "channel_type": "email",
        "sender": "auth@bank.corp",
        "recipient": "user@corp.com",
    }

    # 1. Inspect & quarantine
    resp = client.post("/api/v1/security/inbound-quarantine/inspect", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_quarantined"] is True
    assert "OTP_2FA" in data["detected_risks"]
    assert "782194" not in data["safe_content"]
    assert "[SECURITY_QUARANTINE_TRIGGERED" in data["safe_content"]
    quarantine_id = data["quarantine_id"]
    assert quarantine_id is not None

    # 2. Get record metadata
    meta_resp = client.get(
        f"/api/v1/security/inbound-quarantine/records/{quarantine_id}"
    )
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["quarantine_id"] == quarantine_id
    assert meta["status"] == "ACTIVE"
    assert meta["sender"] == "auth@bank.corp"

    # 3. Release decrypted payload for human viewing
    rel_resp = client.post(
        f"/api/v1/security/inbound-quarantine/records/{quarantine_id}/release"
    )
    assert rel_resp.status_code == 200
    rel = rel_resp.json()
    assert rel["quarantine_id"] == quarantine_id
    assert rel["original_content"] == secret_body
    assert "782194" in rel["original_content"]


def test_get_nonexistent_record_api(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/security/inbound-quarantine/records/quar_nonexistent_123"
    )
    assert resp.status_code == 404


def test_release_nonexistent_record_api(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/inbound-quarantine/records/quar_nonexistent_123/release"
    )
    assert resp.status_code == 410


def test_purge_expired_api(client: TestClient) -> None:
    resp = client.post("/api/v1/security/inbound-quarantine/purge")
    assert resp.status_code == 200
    assert resp.json()["purged_count"] >= 0
