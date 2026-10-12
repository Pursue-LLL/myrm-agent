"""API endpoint tests for Externally Visible Irreversible Action Classification Gate."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.externally_visible_action_router import (
    router as externally_visible_action_router,
)
from app.services.security.externally_visible_action_service import (
    ExternallyVisibleActionService,
    get_externally_visible_action_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ExternallyVisibleActionService()
    test_service.clear_audit_records()
    app = FastAPI()
    app.include_router(externally_visible_action_router)
    app.dependency_overrides[get_externally_visible_action_service] = lambda: test_service
    return TestClient(app)


def test_evaluate_action_endpoint_third_party(client: TestClient) -> None:
    resp = client.post(
        "/security/externally-visible-actions/evaluate",
        json={"tool_name": "send_teammate_message_tool"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "send_teammate_message_tool"
    assert data["is_third_party_visible"] is True
    assert data["requires_mandatory_human_review"] is True
    assert data["hide_allow_always"] is True
    assert data["visibility_scope"] == "THIRD_PARTY_VISIBLE"


def test_evaluate_action_endpoint_internal_safe(client: TestClient) -> None:
    resp = client.post(
        "/security/externally-visible-actions/evaluate",
        json={"tool_name": "file_read_tool"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_third_party_visible"] is False
    assert data["requires_mandatory_human_review"] is False
    assert data["hide_allow_always"] is False
    assert data["visibility_scope"] == "INTERNAL_ONLY"


def test_evaluate_action_endpoint_with_custom_override(client: TestClient) -> None:
    resp = client.post(
        "/security/externally-visible-actions/evaluate",
        json={
            "tool_name": "arbitrary_custom_pipeline",
            "custom_is_third_party_visible": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_third_party_visible"] is True
    assert data["requires_mandatory_human_review"] is True
    assert data["hide_allow_always"] is True


def test_record_audit_and_query_trail_endpoints(client: TestClient) -> None:
    # 1. Record an audit entry
    rec_resp = client.post(
        "/security/externally-visible-actions/record-audit",
        json={
            "action_id": "audit-ep-001",
            "session_id": "sess-test-42",
            "agent_id": "agent-orchestrator",
            "tool_name": "send_email_tool",
            "recipient_or_destination": "investor@venture.com",
            "content_preview": "Quarterly pitch deck preview",
            "is_approved": True,
            "approved_by": "lead-partner",
        },
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["action_id"] == "audit-ep-001"
    assert rec_data["is_approved"] is True
    assert rec_data["approved_by"] == "lead-partner"

    # 2. Query audit trail for matching session
    trail_resp = client.get(
        "/security/externally-visible-actions/audit-trail",
        params={"session_id": "sess-test-42"},
    )
    assert trail_resp.status_code == 200
    trail_data = trail_resp.json()
    assert trail_data["total"] == 1
    assert trail_data["records"][0]["action_id"] == "audit-ep-001"

    # 3. Query audit trail for non-matching session
    empty_resp = client.get(
        "/security/externally-visible-actions/audit-trail",
        params={"session_id": "non-existent-session"},
    )
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["total"] == 0
    assert len(empty_data["records"]) == 0
