"""Integration tests for Spatiotemporal Duality & Saga API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.saga_dual_engine_router import router as saga_dual_engine_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting saga_dual_engine_router."""
    test_app = FastAPI(title="Saga Dual Engine Test App")
    test_app.include_router(saga_dual_engine_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_acquisition_execution_endpoint(client: TestClient) -> None:
    req_payload = {
        "tool_name": "grep_codebase",
        "intent": "ACQUISITION",
        "params": {"query": "TODO"},
        "agent_id": "agent-reader",
    }
    resp = client.post("/api/v1/security/saga-dual-engine/execute", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "ACQUISITION"
    assert "Executed grep_codebase" in data["output"]
    assert data["audit_record"] is None


def test_emission_gates_and_audit_endpoint(client: TestClient) -> None:
    # 1. Emission without connector lease returns 403 Forbidden
    emission_payload = {
        "tool_name": "send_order_email",
        "intent": "EMISSION",
        "params": {"to": "customer@example.com"},
        "agent_id": "agent-mailer",
        "connector_id": "smtp_gateway",
        "connector_host": "smtp.corp.internal",
        "required_scope": "mail:send",
        "hitl_confirmed": True,
    }
    resp_untrusted = client.post("/api/v1/security/saga-dual-engine/execute", json=emission_payload)
    assert resp_untrusted.status_code == 403
    assert "is UNTRUSTED" in resp_untrusted.json()["detail"]

    # 2. Grant trust lease
    lease_payload = {
        "connector_id": "smtp_gateway",
        "host": "smtp.corp.internal",
        "authorized_scopes": ["mail:send"],
        "ttl_seconds": 3600,
    }
    lease_resp = client.post("/api/v1/security/saga-dual-engine/leases", json=lease_payload)
    assert lease_resp.status_code == 201
    lease_data = lease_resp.json()
    lease_id = lease_data["lease_id"]

    # 3. Emission with lease but WITHOUT secondary HITL confirmation returns 428 Precondition Required
    no_hitl_payload = dict(emission_payload)
    no_hitl_payload["hitl_confirmed"] = False
    resp_no_hitl = client.post("/api/v1/security/saga-dual-engine/execute", json=no_hitl_payload)
    assert resp_no_hitl.status_code == 428
    assert "requires explicit secondary HITL confirmation" in resp_no_hitl.json()["detail"]

    # 4. Fully confirmed emission succeeds and returns audit record
    full_payload = dict(emission_payload)
    full_payload["compensator_name"] = "cancel_order_email"
    full_payload["compensation_params"] = {"to": "customer@example.com"}
    resp_ok = client.post("/api/v1/security/saga-dual-engine/execute", json=full_payload)
    assert resp_ok.status_code == 200
    ok_data = resp_ok.json()
    assert ok_data["intent"] == "EMISSION"
    assert ok_data["audit_record"] is not None
    assert ok_data["audit_record"]["connector_id"] == "smtp_gateway"

    # 5. Get audit log
    audit_resp = client.get("/api/v1/security/saga-dual-engine/audit-log")
    assert audit_resp.status_code == 200
    audit_records = audit_resp.json()
    assert len(audit_records) >= 1
    assert any(r["connector_id"] == "smtp_gateway" for r in audit_records)

    # 6. Rollback saga
    rb_resp = client.post("/api/v1/security/saga-dual-engine/rollback")
    assert rb_resp.status_code == 200
    assert rb_resp.json()["success"] is True

    # 7. Revoke lease
    rev_resp = client.post(
        "/api/v1/security/saga-dual-engine/leases/revoke",
        json={"lease_id": lease_id},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["revoked"] is True
