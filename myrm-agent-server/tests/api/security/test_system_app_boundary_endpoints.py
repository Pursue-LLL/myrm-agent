"""
[POS] tests/api/security/test_system_app_boundary_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.system_app_boundary_router
[OUTPUT] Integration tests for System App Privacy Boundary REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.system_app_boundary_router import (
    router as system_app_boundary_router,
)
from app.services.security.system_app_boundary_service import (
    SystemAppBoundaryService,
    get_system_app_boundary_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = SystemAppBoundaryService()
    app = FastAPI()
    app.include_router(system_app_boundary_router)
    app.dependency_overrides[get_system_app_boundary_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_and_scope_rule(client: TestClient) -> None:
    """Test setting scoping rules and evaluating read requests within and outside boundary."""
    # 1. Configure Notes boundary
    rule_resp = client.post(
        "/system-app-boundary/rules",
        json={
            "app_type": "NOTES",
            "allowed_containers": ["Work Notes"],
            "allow_mutations_without_prompt": False,
        },
    )
    assert rule_resp.status_code == 200
    assert rule_resp.json()["app_type"] == "NOTES"

    # 2. Query declared rule
    get_rule = client.get("/system-app-boundary/rules/NOTES")
    assert get_rule.status_code == 200
    assert "Work Notes" in get_rule.json()["allowed_containers"]

    # 3. Read within allowed container
    read_ok = client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-01",
            "session_id": "sess-api-01",
            "app_type": "NOTES",
            "operation_type": "READ_ONLY",
            "target_container": "Work Notes",
            "payload_summary": "Read sprint memo",
        },
    )
    assert read_ok.status_code == 200
    assert read_ok.json()["decision"] == "PERMITTED_SILENT"
    assert read_ok.json()["is_allowed"] is True

    # 4. Read outside allowed container
    read_blocked = client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-02",
            "session_id": "sess-api-01",
            "app_type": "NOTES",
            "operation_type": "READ_ONLY",
            "target_container": "Private Passwords",
            "payload_summary": "Scan passwords",
        },
    )
    assert read_blocked.status_code == 200
    assert read_blocked.json()["decision"] == "BOUNDARY_VIOLATION_BLOCKED"
    assert read_blocked.json()["is_allowed"] is False


def test_endpoint_write_consent_workflow(client: TestClient) -> None:
    """Test mutation consent requirement and subsequent grant workflow."""
    client.post(
        "/system-app-boundary/rules",
        json={
            "app_type": "NOTES",
            "allowed_containers": ["Work Notes"],
            "allow_mutations_without_prompt": False,
        },
    )

    # 1. Mutation requires consent
    held_resp = client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-write",
            "session_id": "sess-api-02",
            "app_type": "NOTES",
            "operation_type": "MUTATE_WRITE",
            "target_container": "Work Notes",
            "payload_summary": "Append new task to project note",
        },
    )
    assert held_resp.status_code == 200
    assert held_resp.json()["decision"] == "REQUIRE_WRITE_CONSENT"
    assert held_resp.json()["is_allowed"] is False

    # 2. Check pending list
    pending = client.get("/system-app-boundary/consent/pending")
    assert pending.status_code == 200
    items = pending.json()
    assert len(items) == 1
    assert items[0]["request_id"] == "api-req-write"

    # 3. Grant consent
    grant_resp = client.post(
        "/system-app-boundary/consent/grant",
        json={
            "request_id": "api-req-write",
            "approver_note": "User confirmed note edit",
        },
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["decision"] == "PERMITTED_SILENT"
    assert grant_resp.json()["is_allowed"] is True

    # 4. Pending empty
    pending_after = client.get("/system-app-boundary/consent/pending")
    assert len(pending_after.json()) == 0


def test_endpoint_consent_reject_and_not_found(client: TestClient) -> None:
    """Test rejecting write consent and handling non-existent grant requests."""
    client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-rej",
            "session_id": "sess-api-03",
            "app_type": "MAIL",
            "operation_type": "MUTATE_WRITE",
            "target_container": "Default",
            "payload_summary": "Send unexpected email",
        },
    )

    # Reject
    rej_resp = client.post(
        "/system-app-boundary/consent/reject",
        json={"request_id": "api-req-rej", "reason": "User denied sending"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["rejected"] is True

    # Approve non-existent -> 404
    not_found = client.post(
        "/system-app-boundary/consent/grant",
        json={"request_id": "api-req-rej"},
    )
    assert not_found.status_code == 404


def test_endpoint_lockdown_lifecycle(client: TestClient) -> None:
    """Test emergency lockdown trigger, block, and release via REST."""
    # Lockdown Mail
    lock_resp = client.post("/system-app-boundary/lockdown/MAIL")
    assert lock_resp.status_code == 200
    assert lock_resp.json()["is_locked_down"] is True

    # Evaluation blocked
    eval_locked = client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-locked",
            "session_id": "sess-api-04",
            "app_type": "MAIL",
            "operation_type": "READ_ONLY",
            "target_container": "Inbox",
            "payload_summary": "Read email headers",
        },
    )
    assert eval_locked.status_code == 200
    assert eval_locked.json()["decision"] == "EMERGENCY_APP_LOCKED"
    assert eval_locked.json()["is_allowed"] is False

    # Unlock Mail
    unlock_resp = client.post("/system-app-boundary/unlock/MAIL")
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["is_locked_down"] is False


def test_endpoint_audit_and_metrics(client: TestClient) -> None:
    """Test fetching audit trails and cumulative metric counters."""
    client.post(
        "/system-app-boundary/evaluate",
        json={
            "request_id": "api-req-telemetry",
            "session_id": "sess-api-05",
            "app_type": "CALENDAR",
            "operation_type": "READ_ONLY",
            "target_container": "Default",
            "payload_summary": "Get schedule",
        },
    )

    audit_resp = client.get("/system-app-boundary/audit?limit=10")
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()) >= 1

    metrics_resp = client.get("/system-app-boundary/metrics")
    assert metrics_resp.status_code == 200
    assert "requests_evaluated_total" in metrics_resp.json()
