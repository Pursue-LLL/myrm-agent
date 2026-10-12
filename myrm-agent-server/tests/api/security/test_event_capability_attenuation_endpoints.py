"""
[POS] tests/api/security/test_event_capability_attenuation_endpoints.py
[INPUT] app.api.security.event_capability_attenuation_router, app.services.security.event_capability_attenuation_service
[OUTPUT] endpoint tests

API endpoint tests for Event-Triggered Capability Attenuation & Async Approval Bridge Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.event_capability_attenuation import (
    EventSignatureVerifier,
)

from app.api.security.event_capability_attenuation_router import (
    router as event_capability_attenuation_router,
)
from app.services.security.event_capability_attenuation_service import (
    EventCapabilityAttenuationService,
    get_event_capability_attenuation_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = EventCapabilityAttenuationService()
    app = FastAPI()
    app.include_router(event_capability_attenuation_router)
    app.dependency_overrides[get_event_capability_attenuation_service] = (
        lambda: test_service
    )
    return TestClient(app)


def test_register_and_ingest_event_endpoints(client: TestClient) -> None:
    """Test POST /event-attenuation/register-secret and /ingest-event."""
    source = "github_mcp"
    secret = "hmac_key_top_secret"

    # 1. Register secret
    reg_res = client.post(
        "/event-attenuation/register-secret",
        json={"source_name": source, "secret_key": secret},
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["registered"] is True

    # 2. Ingest signed event
    payload = '{"event": "push", "ref": "refs/heads/main"}'
    verifier = EventSignatureVerifier()
    verifier.register_source_secret(source, secret)
    sig = verifier.compute_signature(source, payload.encode("utf-8"))

    ingest_res = client.post(
        "/event-attenuation/ingest-event",
        json={
            "event_id": "evt-api-01",
            "source_name": source,
            "event_type": "push",
            "timestamp": time.time(),
            "raw_payload_text": payload,
            "signature": sig,
            "auto_bind_session_id": "sess-api-01",
        },
    )
    assert ingest_res.status_code == 200
    i_data = ingest_res.json()
    assert i_data["is_verified"] is True
    assert i_data["bound_scope"] == "LOW_TRUST_EVENT_SCOPE"


def test_scope_and_evaluation_endpoints(client: TestClient) -> None:
    """Test GET/PUT /event-attenuation/scope/{session_id} and POST /evaluate-tool."""
    session_id = "sess-scope-01"

    # Default scope
    get_s = client.get(f"/event-attenuation/scope/{session_id}")
    assert get_s.status_code == 200
    assert get_s.json()["active_scope"] == "USER_INTERACTIVE"

    # Update scope to LOW_TRUST_EVENT_SCOPE
    put_s = client.put(
        f"/event-attenuation/scope/{session_id}",
        json={"scope": "LOW_TRUST_EVENT_SCOPE"},
    )
    assert put_s.status_code == 200
    assert put_s.json()["active_scope"] == "LOW_TRUST_EVENT_SCOPE"

    # Evaluate tool
    eval_ro = client.post(
        "/event-attenuation/evaluate-tool",
        json={"session_id": session_id, "tool_name": "file_read"},
    )
    assert eval_ro.status_code == 200
    assert eval_ro.json()["is_allowed"] is True

    eval_bl = client.post(
        "/event-attenuation/evaluate-tool",
        json={"session_id": session_id, "tool_name": "rm_rf"},
    )
    assert eval_bl.status_code == 200
    assert eval_bl.json()["is_allowed"] is False
    assert eval_bl.json()["risk_level"] in ("HIGH", "CRITICAL")


def test_ticket_lifecycle_and_token_endpoints(client: TestClient) -> None:
    """Test ticket creation, approval, token consumption, and metrics."""
    # 1. Create ticket
    ticket_payload = {
        "session_id": "sess-tkt-api",
        "requested_tool": "shell_exec",
        "risk_level": "HIGH",
        "action_description": "Run shell deployment script",
        "diff_payload": "echo 'deploying'",
        "channels": [{"channel_type": "feishu", "target_id": "feishu-bot-123"}],
    }
    create_res = client.post("/event-attenuation/tickets", json=ticket_payload)
    assert create_res.status_code == 201
    ticket = create_res.json()
    ticket_id = ticket["ticket_id"]
    assert ticket["status"] == "PENDING"

    # 2. Get ticket by ID
    get_tkt = client.get(f"/event-attenuation/tickets/{ticket_id}")
    assert get_tkt.status_code == 200
    assert get_tkt.json()["ticket_id"] == ticket_id

    # 3. List tickets
    list_res = client.get("/event-attenuation/tickets")
    assert list_res.status_code == 200
    assert any(t["ticket_id"] == ticket_id for t in list_res.json())

    # 4. Approve ticket
    approve_res = client.post(
        f"/event-attenuation/tickets/{ticket_id}/approve",
        json={"decided_by": "oncall_alice", "decision_reason": "Approved on mobile"},
    )
    assert approve_res.status_code == 200
    app_data = approve_res.json()
    assert app_data["ticket"]["status"] == "APPROVED"
    token = app_data["execution_token"]
    assert len(token) > 0

    # 5. Consume token
    consume_res = client.post(
        "/event-attenuation/consume-token",
        json={"token": token},
    )
    assert consume_res.status_code == 200
    assert consume_res.json()["is_valid"] is True
    assert consume_res.json()["matched_ticket_id"] == ticket_id

    # Re-consume fails
    re_consume = client.post("/event-attenuation/consume-token", json={"token": token})
    assert re_consume.status_code == 200
    assert re_consume.json()["is_valid"] is False

    # 6. Reject another ticket
    t2_res = client.post("/event-attenuation/tickets", json=ticket_payload)
    t2_id = t2_res.json()["ticket_id"]
    reject_res = client.post(
        f"/event-attenuation/tickets/{t2_id}/reject",
        json={"decided_by": "secops_bob", "decision_reason": "Denied"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "REJECTED"

    # 7. Metrics
    metrics_res = client.get("/event-attenuation/metrics")
    assert metrics_res.status_code == 200
    assert metrics_res.json()["tickets_created"] >= 2
