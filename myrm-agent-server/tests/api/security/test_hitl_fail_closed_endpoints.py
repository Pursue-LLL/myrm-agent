"""Integration tests for HITL Approval Fail-Closed Safety Gate API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.hitl_fail_closed_router import (
    router as hitl_fail_closed_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting hitl_fail_closed_router."""
    test_app = FastAPI(title="HITL Fail Closed Test App")
    test_app.include_router(hitl_fail_closed_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_endpoint_disconnected(client: TestClient) -> None:
    payload = {
        "tool_name": "bash_execute",
        "arguments": {"command": "echo test"},
        "channel_connected": False,
    }
    resp = client.post("/api/v1/security/hitl-fail-closed/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_execution_permitted"] is False
    assert data["approval_decision"] == "REJECTED_FAIL_CLOSED"
    assert data["fail_closed_reason"] == "CHANNEL_DISCONNECTED"


def test_evaluate_endpoint_timeout(client: TestClient) -> None:
    payload = {
        "tool_name": "bash_execute",
        "arguments": {"command": "echo test"},
        "simulate_timeout": True,
    }
    resp = client.post("/api/v1/security/hitl-fail-closed/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_execution_permitted"] is False
    assert data["approval_decision"] == "REJECTED_FAIL_CLOSED"
    assert data["fail_closed_reason"] == "TIMEOUT"


def test_evaluate_endpoint_user_rejected(client: TestClient) -> None:
    payload = {
        "tool_name": "bash_execute",
        "arguments": {"command": "echo test"},
        "user_approval": False,
    }
    resp = client.post("/api/v1/security/hitl-fail-closed/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_execution_permitted"] is False
    assert data["approval_decision"] == "REJECTED_USER"


def test_evaluate_endpoint_approved_with_guard_block(client: TestClient) -> None:
    payload = {
        "tool_name": "bash_execute",
        "arguments": {"command": "rm -rf /"},
        "user_approval": True,
    }
    resp = client.post("/api/v1/security/hitl-fail-closed/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_execution_permitted"] is False
    assert data["approval_decision"] == "APPROVED"
    assert data["guard_verdict"] == "BLOCKED_PHYSICAL_INVARIANT"


def test_evaluate_endpoint_approved_and_passed(client: TestClient) -> None:
    payload = {
        "tool_name": "bash_execute",
        "arguments": {"command": "git status"},
        "user_approval": True,
    }
    resp = client.post("/api/v1/security/hitl-fail-closed/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_execution_permitted"] is True
    assert data["approval_decision"] == "APPROVED"
    assert data["guard_verdict"] == "PASSED"


def test_verify_guard_endpoint(client: TestClient) -> None:
    # 1. Blocked
    payload_blocked = {
        "tool_name": "file_writer",
        "arguments": {"path": "/etc/passwd", "content": "fake"},
    }
    resp_b = client.post("/api/v1/security/hitl-fail-closed/verify-guard", json=payload_blocked)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["is_permitted"] is False
    assert data_b["guard_verdict"] == "BLOCKED_HIGH_RISK_PATTERN"

    # 2. Passed
    payload_passed = {
        "tool_name": "file_writer",
        "arguments": {"path": "workspace/notes.txt", "content": "meeting notes"},
    }
    resp_p = client.post("/api/v1/security/hitl-fail-closed/verify-guard", json=payload_passed)
    assert resp_p.status_code == 200
    data_p = resp_p.json()
    assert data_p["is_permitted"] is True
    assert data_p["guard_verdict"] == "PASSED"
