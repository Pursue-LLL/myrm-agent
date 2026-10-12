"""API endpoint tests for Pre-Flight Irreversible Write Interception and Emergency Kill Switch."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.irreversible_write_guard_router import (
    router as irreversible_write_guard_router,
)
from app.services.security.irreversible_write_guard_service import (
    IrreversibleWriteGuardService,
    get_irreversible_write_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = IrreversibleWriteGuardService()
    app = FastAPI()
    app.include_router(irreversible_write_guard_router, prefix="/api/v1/security")
    app.dependency_overrides[get_irreversible_write_guard_service] = lambda: test_service
    return TestClient(app)


def test_intercept_endpoint(client: TestClient) -> None:
    # 1. Safe tool
    resp_safe = client.post(
        "/api/v1/security/irreversible-write-guard/intercept",
        json={
            "tool_name": "list_files",
            "arguments": {"directory": "/workspace"},
            "session_id": "sess_api_safe",
        },
    )
    assert resp_safe.status_code == 200
    data_safe = resp_safe.json()
    assert data_safe["intercepted"] is False
    assert data_safe["intent"] is None

    # 2. Irreversible git push
    resp_git = client.post(
        "/api/v1/security/irreversible-write-guard/intercept",
        json={
            "tool_name": "git_push",
            "arguments": {"remote": "origin", "branch": "main", "force": "true"},
            "session_id": "sess_api_git",
        },
    )
    assert resp_git.status_code == 200
    data_git = resp_git.json()
    assert data_git["intercepted"] is True
    assert data_git["intent"] is not None
    assert data_git["intent"]["domain"] == "git_push"
    assert data_git["intent"]["blast_radius"]["risk_level"] == "critical"
    assert data_git["intent"]["status"] == "pending_confirmation"


def test_approve_endpoint(client: TestClient) -> None:
    # Intercept email
    resp_intercept = client.post(
        "/api/v1/security/irreversible-write-guard/intercept",
        json={
            "tool_name": "send_email",
            "arguments": {"to": "boss@corp.com", "subject": "Update", "body": "Weekly review"},
            "session_id": "sess_api_email",
        },
    )
    intent_id = resp_intercept.json()["intent"]["intent_id"]

    # Approve
    resp_approve = client.post(
        f"/api/v1/security/irreversible-write-guard/approve/{intent_id}",
        json={"approver": "supervisor_alice"},
    )
    assert resp_approve.status_code == 200
    data_appr = resp_approve.json()
    assert data_appr["status"] == "approved"
    assert "supervisor_alice" in data_appr["resolution_reason"]

    # Second approval fails
    resp_re_approve = client.post(
        f"/api/v1/security/irreversible-write-guard/approve/{intent_id}",
        json={"approver": "supervisor_alice"},
    )
    assert resp_re_approve.status_code == 400

    # Non-existent intent
    resp_404 = client.post(
        "/api/v1/security/irreversible-write-guard/approve/non_existent_id",
        json={"approver": "someone"},
    )
    assert resp_404.status_code == 404


def test_emergency_kill_endpoint(client: TestClient) -> None:
    # Intercept payment
    resp_intercept = client.post(
        "/api/v1/security/irreversible-write-guard/intercept",
        json={
            "tool_name": "stripe_charge",
            "arguments": {"amount": "50000", "currency": "USD", "recipient": "fake_store"},
            "session_id": "sess_api_pay",
        },
    )
    intent_id = resp_intercept.json()["intent"]["intent_id"]

    # Trigger Emergency Kill Switch
    resp_kill = client.post(
        f"/api/v1/security/irreversible-write-guard/kill/{intent_id}",
        json={"reason": "Suspected payment hijacking attempt"},
    )
    assert resp_kill.status_code == 200
    kill_data = resp_kill.json()
    assert kill_data["killed"] is True
    assert "hijacking" in kill_data["reason"]

    # Verify intent state via GET
    resp_get = client.get(f"/api/v1/security/irreversible-write-guard/intents/{intent_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == "killed_aborted"
    assert resp_get.json()["arguments"] == {}

    # Non-existent intent
    resp_kill_404 = client.post(
        "/api/v1/security/irreversible-write-guard/kill/unknown_intent_id",
        json={"reason": "Abort"},
    )
    assert resp_kill_404.status_code == 404


def test_pending_and_contracts_endpoints(client: TestClient) -> None:
    # Intercept database write
    resp_intercept = client.post(
        "/api/v1/security/irreversible-write-guard/intercept",
        json={
            "tool_name": "sql_execute_write",
            "arguments": {"sql": "DROP TABLE users;", "table": "users"},
            "session_id": "sess_api_db",
        },
    )
    assert resp_intercept.status_code == 200

    # List pending
    resp_pending = client.get("/api/v1/security/irreversible-write-guard/pending?session_id=sess_api_db")
    assert resp_pending.status_code == 200
    pending_list = resp_pending.json()
    assert len(pending_list) == 1
    assert pending_list[0]["tool_name"] == "sql_execute_write"

    # List contracts
    resp_contracts = client.get("/api/v1/security/irreversible-write-guard/contracts")
    assert resp_contracts.status_code == 200
    assert len(resp_contracts.json()) >= 8

    # Register custom contract
    resp_reg = client.post(
        "/api/v1/security/irreversible-write-guard/contracts",
        json={
            "tool_name": "k8s_delete_cluster",
            "domain": "database",
            "description": "Delete Kubernetes production cluster",
            "default_risk_level": "critical",
        },
    )
    assert resp_reg.status_code == 201
    assert resp_reg.json()["tool_name"] == "k8s_delete_cluster"
