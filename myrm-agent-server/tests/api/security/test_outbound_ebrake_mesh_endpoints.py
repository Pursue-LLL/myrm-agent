"""
[POS] tests/api/security/test_outbound_ebrake_mesh_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.outbound_ebrake_mesh_router
[OUTPUT] Integration tests for Outbound E-Brake & Chief of Staff Mesh REST endpoints

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.outbound_ebrake_mesh_router import (
    router as outbound_ebrake_mesh_router,
)
from app.services.security.outbound_ebrake_mesh_service import (
    OutboundEBrakeMeshService,
    get_outbound_ebrake_mesh_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = OutboundEBrakeMeshService()
    app = FastAPI()
    app.include_router(outbound_ebrake_mesh_router)
    app.dependency_overrides[get_outbound_ebrake_mesh_service] = lambda: service
    return TestClient(app)


def test_endpoint_inspect_outbound_action(client: TestClient) -> None:
    """Test ghost pre-flight inspection endpoint."""
    # 1. Clean internal
    resp1 = client.post(
        "/outbound-ebrake-mesh/inspect",
        json={
            "action_type": "EMAIL_DISPATCH",
            "destination_target": "ops@myrm.internal",
            "payload_text": "System metrics operational.",
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["is_safe_to_queue"] is True
    assert resp1.json()["risk_tier"] == "INTERNAL_SAFE"

    # 2. Exfiltration blocked
    resp2 = client.post(
        "/outbound-ebrake-mesh/inspect",
        json={
            "action_type": "EMAIL_DISPATCH",
            "destination_target": "attacker@gmail.com",
            "payload_text": "Here is the key: ghp_123456789012345678901234567890123456",
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["is_safe_to_queue"] is False
    assert resp2.json()["risk_tier"] == "PROHIBITED_LEAK"
    assert "GITHUB_PAT" in resp2.json()["tainted_tokens_detected"]


def test_endpoint_action_lifecycle(client: TestClient) -> None:
    """Test enqueue, get, cancel, and flush endpoints."""
    # 1. Enqueue
    enq_resp = client.post(
        "/outbound-ebrake-mesh/actions/enqueue",
        json={
            "task_id": "task-api-test-01",
            "action_type": "EMAIL_DISPATCH",
            "destination_target": "team@corp.internal",
            "payload_text": "Quarterly plan kickoff",
            "grace_period_seconds": 15.0,
        },
    )
    assert enq_resp.status_code == 201
    action_data = enq_resp.json()
    action_id: str = action_data["action_id"]
    assert action_data["status"] == "QUEUED_IN_GRACE_PERIOD"

    # 2. Get action
    get_resp = client.get(f"/outbound-ebrake-mesh/actions/{action_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["action_id"] == action_id

    # 3. List queued
    list_resp = client.get("/outbound-ebrake-mesh/actions/queued")
    assert list_resp.status_code == 200
    assert any(x["action_id"] == action_id for x in list_resp.json())

    # 4. Cancel action
    cancel_resp = client.post(
        f"/outbound-ebrake-mesh/actions/{action_id}/cancel",
        json={"reason": "Manual operator override"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["cancelled"] is True

    # 5. Verify cancelled
    get_again = client.get(f"/outbound-ebrake-mesh/actions/{action_id}")
    assert get_again.status_code == 200
    assert get_again.json()["status"] == "CANCELLED_BY_USER"

    # 6. Enqueue another and flush immediately
    enq2_resp = client.post(
        "/outbound-ebrake-mesh/actions/enqueue",
        json={
            "task_id": "task-api-test-02",
            "action_type": "WEBHOOK_CALL",
            "destination_target": "https://slack.com/api/chat",
            "payload_text": "Live status update",
            "grace_period_seconds": 20.0,
        },
    )
    assert enq2_resp.status_code == 201
    act2_id: str = enq2_resp.json()["action_id"]

    flush_resp = client.post(f"/outbound-ebrake-mesh/actions/{act2_id}/flush")
    assert flush_resp.status_code == 200
    assert flush_resp.json()["flushed"] is True


def test_endpoint_emergency_e_brake(client: TestClient) -> None:
    """Test out-of-band physical e-brake trigger, status, and reset endpoints."""
    # 1. Enqueue pending action
    client.post(
        "/outbound-ebrake-mesh/actions/enqueue",
        json={
            "task_id": "task-stop-01",
            "action_type": "SOCIAL_POST",
            "destination_target": "x.com/post",
            "payload_text": "Draft social post",
            "grace_period_seconds": 30.0,
        },
    )

    # 2. Trigger E-Brake
    trig_resp = client.post(
        "/outbound-ebrake-mesh/ebrake/trigger",
        json={"reason": "Physical STOP button pressed"},
    )
    assert trig_resp.status_code == 200
    assert trig_resp.json()["aborted_actions_count"] >= 1

    # 3. Check status
    st_resp = client.get("/outbound-ebrake-mesh/ebrake/status")
    assert st_resp.status_code == 200
    st_data = st_resp.json()
    assert st_data["is_e_brake_active"] is True
    assert st_data["trigger_reason"] == "Physical STOP button pressed"

    # 4. Reset E-Brake
    reset_resp = client.post("/outbound-ebrake-mesh/ebrake/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["reset"] is True

    # 5. Confirm status reset
    st_after = client.get("/outbound-ebrake-mesh/ebrake/status")
    assert st_after.status_code == 200
    assert st_after.json()["is_e_brake_active"] is False


def test_endpoint_calendar_negotiation_and_metrics(client: TestClient) -> None:
    """Test A2A privacy-preserving calendar negotiation and operational metrics endpoints."""
    slots_a = [
        {"slot_index": 0, "start_time_iso": "2026-10-10T10:00:00Z", "is_free": True, "preference_score": 0.8},
        {"slot_index": 1, "start_time_iso": "2026-10-10T10:30:00Z", "is_free": False, "preference_score": 0.0},
    ]
    slots_b = [
        {"slot_index": 0, "start_time_iso": "2026-10-10T10:00:00Z", "is_free": True, "preference_score": 0.9},
        {"slot_index": 1, "start_time_iso": "2026-10-10T10:30:00Z", "is_free": True, "preference_score": 0.5},
    ]

    neg_resp = client.post(
        "/outbound-ebrake-mesh/calendar/negotiate",
        json={
            "party_a_id": "cos-alpha",
            "party_b_id": "cos-beta",
            "party_a_slots": slots_a,
            "party_b_slots": slots_b,
        },
    )
    assert neg_resp.status_code == 200
    n_data = neg_resp.json()
    assert n_data["privacy_preserved"] is True
    assert len(n_data["matched_slots"]) == 1
    assert n_data["optimal_slot"] is not None
    assert n_data["optimal_slot"]["slot_index"] == 0

    # Operational metrics
    m_resp = client.get("/outbound-ebrake-mesh/metrics")
    assert m_resp.status_code == 200
    assert m_resp.json()["calendar_negotiations_total"] >= 1
