"""Integration tests for HITL Denial API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/hitl-denial/* endpoints.

[OUTPUT]
- Verified JSON responses for processing manual denials and generating synthetic tool results.

[POS]
- Server integration test suite for AgentScope-Java #2546 HITL denial handling.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.hitl_denial_router import (
    get_hitl_denial_service,
)
from app.api.security.hitl_denial_router import (
    router as hitl_denial_router,
)
from app.schemas.hitl_denial import DenialResolutionPolicyDto
from app.services.security.hitl_denial_service import HitlDenialService


@pytest.fixture(scope="function")
def isolated_service() -> HitlDenialService:
    """Fixture providing isolated service instance."""
    return HitlDenialService()


@pytest.fixture(scope="function")
def client(isolated_service: HitlDenialService) -> TestClient:
    """Fixture providing test client mounting hitl_denial_router."""
    test_app = FastAPI(title="HITL Denial Test App")
    test_app.dependency_overrides[get_hitl_denial_service] = lambda: isolated_service
    test_app.include_router(hitl_denial_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_process_hitl_denials_partial_continue(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/hitl-denial/process",
        json={
            "denied_items": [
                {
                    "tool_call_id": "call_1",
                    "tool_name": "bash",
                    "reason": "Forbidden command",
                    "custom_feedback": "Use cat instead",
                }
            ],
            "total_tool_calls_in_step": 2,
            "override_policy": DenialResolutionPolicyDto.CONTINUE.value,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_tools_denied"] is False
    assert data["total_requested"] == 2
    assert data["total_denied"] == 1
    assert data["stop_requested"] is False
    assert len(data["synthetic_results"]) == 1
    assert "[Action Denied by User]" in data["synthetic_results"][0]["output"]
    assert "Use cat instead" in data["synthetic_results"][0]["output"]


def test_process_hitl_denials_all_denied_stop(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/hitl-denial/process",
        json={
            "denied_items": [
                {
                    "tool_call_id": "call_danger",
                    "tool_name": "delete_db",
                    "reason": "Production hazard",
                }
            ],
            "total_tool_calls_in_step": 1,
            "override_policy": DenialResolutionPolicyDto.STOP.value,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_tools_denied"] is True
    assert data["stop_requested"] is True
    assert data["resolution_action"] == DenialResolutionPolicyDto.STOP.value
