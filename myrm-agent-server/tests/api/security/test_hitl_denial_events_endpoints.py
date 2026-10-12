"""API tests for HITL Denial Events endpoints in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.hitl_denial_events_router import (
    router as hitl_denial_events_router,
)
from app.services.security.hitl_denial_events_service import (
    HitlDenialEventsService,
    get_hitl_denial_events_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    service = HitlDenialEventsService()
    app.dependency_overrides[get_hitl_denial_events_service] = lambda: service
    app.include_router(hitl_denial_events_router, prefix="/api/v1/security")
    return TestClient(app)


def test_post_process_hitl_decisions_denied_with_custom_reason(
    client: TestClient,
) -> None:
    payload = {
        "session_id": "api_sess_1",
        "step_id": "step_1",
        "tool_calls": [
            {
                "id": "tc_1",
                "name": "network_call",
                "arguments": {"url": "https://external.org"},
            },
            {
                "id": "tc_2",
                "name": "query_db",
                "arguments": {"sql": "SELECT 1"},
            },
        ],
        "decisions": [
            {
                "tool_call_id": "tc_1",
                "tool_name": "network_call",
                "confirmed": False,
                "reason": "Outbound egress is locked.",
            },
            {
                "tool_call_id": "tc_2",
                "tool_name": "query_db",
                "confirmed": True,
            },
        ],
    }

    response = client.post("/api/v1/security/hitl-denials/process", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["session_id"] == "api_sess_1"
    assert data["total_calls"] == 2
    assert data["confirmed_count"] == 1
    assert data["denied_count"] == 1
    assert data["all_denied"] is False
    assert data["can_resume"] is True
    assert data["all_tools_denied_event"] is None

    assert len(data["tool_result_events"]) == 2
    denied_event = data["tool_result_events"][0]
    assert denied_event["tool_call_id"] == "tc_1"
    assert denied_event["state"] == "DENIED"
    assert denied_event["output_text"] == "Outbound egress is locked."

    allowed_event = data["tool_result_events"][1]
    assert allowed_event["tool_call_id"] == "tc_2"
    assert allowed_event["state"] == "ALLOWED"


def test_post_process_hitl_decisions_all_denied_halt(
    client: TestClient,
) -> None:
    payload = {
        "session_id": "api_sess_2",
        "step_id": "step_2",
        "tool_calls": [
            {
                "id": "tc_danger",
                "name": "rm_destructive",
                "arguments": {"path": "/var/data"},
            }
        ],
        "decisions": [
            {
                "tool_call_id": "tc_danger",
                "tool_name": "rm_destructive",
                "confirmed": False,
                "reason": "Deleting production data is forbidden.",
            }
        ],
        "policy": "HALT",
    }

    response = client.post("/api/v1/security/hitl-denials/process", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["all_denied"] is True
    assert data["can_resume"] is False
    assert data["all_tools_denied_event"] is not None
    assert data["all_tools_denied_event"]["should_stop"] is True
    assert data["all_tools_denied_event"]["policy_applied"] == "HALT"


def test_post_process_hitl_decisions_all_denied_resume(
    client: TestClient,
) -> None:
    payload = {
        "session_id": "api_sess_3",
        "step_id": "step_3",
        "tool_calls": [
            {
                "id": "tc_3",
                "name": "lookup_docs",
                "arguments": {"topic": "sec"},
            }
        ],
        "decisions": [
            {
                "tool_call_id": "tc_3",
                "tool_name": "lookup_docs",
                "confirmed": False,
                "reason": "Search in index instead.",
            }
        ],
        "policy": "RESUME_WITH_FEEDBACK",
    }

    response = client.post("/api/v1/security/hitl-denials/process", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["all_denied"] is True
    assert data["can_resume"] is True
    assert data["terminal_reason"] is None
    assert data["all_tools_denied_event"] is not None
    assert data["all_tools_denied_event"]["should_stop"] is False
    assert data["all_tools_denied_event"]["policy_applied"] == "RESUME_WITH_FEEDBACK"


def test_get_policies_config_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/security/hitl-denials/policies")
    assert response.status_code == 200
    data = response.json()

    assert "HALT" in data["available_policies"]
    assert "RESUME_WITH_FEEDBACK" in data["available_policies"]
    assert data["default_policy"] == "HALT"
    assert "bash_exec" in data["strict_halt_tools"]
