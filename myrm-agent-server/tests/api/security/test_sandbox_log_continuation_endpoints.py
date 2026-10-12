"""Integration tests for Sandbox Log Redaction and Execution Continuation Audit endpoints."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sandbox_log_continuation_router import (
    router as sandbox_log_continuation_router,
)
from app.services.security.sandbox_log_continuation_service import (
    SandboxLogContinuationService,
    get_sandbox_log_continuation_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> SandboxLogContinuationService:
    """Fixture providing an isolated in-memory service instance."""
    return SandboxLogContinuationService()


@pytest.fixture(scope="function")
def client(isolated_service: SandboxLogContinuationService) -> TestClient:
    """Fixture providing test client mounting sandbox_log_continuation_router."""
    test_app = FastAPI(title="Sandbox Log Continuation Test App")
    test_app.dependency_overrides[get_sandbox_log_continuation_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        sandbox_log_continuation_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_redact_endpoint(client: TestClient) -> None:
    payload = {
        "raw_text": "Error connecting to db using postgresql://postgres:mypassword123@prod-db:5432/main with api_key=sk-1234567890abcdef12345678",
        "command": "psql -U postgres --password=mypassword123",
        "command_args": ["-c", "SELECT 1"],
    }
    resp = client.post(
        "/api/v1/security/sandbox-log-continuation/redact",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["redaction_count"] >= 2
    assert "mypassword123" not in data["redacted_text"]
    assert "sk-1234567890abcdef12345678" not in data["redacted_text"]
    assert "mypassword123" not in data["redacted_command"]


def test_runs_heartbeat_and_audit_endpoints(client: TestClient) -> None:
    now = time.time()

    # 1. Register run
    reg_payload = {
        "run_id": "run-api-001",
        "task_id": "task-api-99",
        "assignee_agent_id": "agent-lead",
        "is_terminal": False,
    }
    reg_resp = client.post(
        "/api/v1/security/sandbox-log-continuation/runs",
        json=reg_payload,
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["run_id"] == "run-api-001"
    assert reg_data["task_id"] == "task-api-99"

    # 2. Post heartbeat
    hb_payload = {
        "run_id": "run-api-001",
        "timestamp": now,
        "seq": 1,
        "status": "running",
        "metadata": {"worker": "sandbox-k8s-01"},
    }
    hb_resp = client.post(
        "/api/v1/security/sandbox-log-continuation/heartbeat",
        json=hb_payload,
    )
    assert hb_resp.status_code == 200
    hb_data = hb_resp.json()
    assert hb_data["success"] is True

    # 3. Audit continuation - valid resume
    audit_payload = {
        "task_id": "task-api-99",
        "requesting_agent_id": "agent-lead",
        "proposed_run_id": "run-api-002",
        "resume_source_run_id": "run-api-001",
        "max_heartbeat_gap_seconds": 60.0,
    }
    audit_resp = client.post(
        "/api/v1/security/sandbox-log-continuation/audit",
        json=audit_payload,
    )
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["is_resumable"] is True
    assert audit_data["status"] == "VALID"

    # 4. Audit continuation - ownership mismatch
    mismatch_payload = {
        "task_id": "task-api-99",
        "requesting_agent_id": "agent-imposter",
        "proposed_run_id": "run-api-003",
        "resume_source_run_id": "run-api-001",
        "max_heartbeat_gap_seconds": 60.0,
    }
    mismatch_resp = client.post(
        "/api/v1/security/sandbox-log-continuation/audit",
        json=mismatch_payload,
    )
    assert mismatch_resp.status_code == 200
    mismatch_data = mismatch_resp.json()
    assert mismatch_data["is_resumable"] is False
    assert mismatch_data["status"] == "OWNERSHIP_MISMATCH"
