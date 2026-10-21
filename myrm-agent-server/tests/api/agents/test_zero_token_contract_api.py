"""Unit tests for Zero-Token Fleet Runtime Event Mirror Contract API (Item 48).

[INPUT]
- app.api.agents.zero_token_contract_router.router
- app.services.agent.zero_token_contract_service.ZeroTokenContractService

[OUTPUT]
- Pytest test cases validating single event mirror (0 tokens), batch event mirror,
  Doctor LLM intercepting for protected viz surfaces, and audit reporting.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_zero_token_contract_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.zero_token_contract_router import (
    get_service,
)
from app.api.agents.zero_token_contract_router import (
    router as zero_token_contract_router,
)
from app.services.agent.zero_token_contract_service import (
    ZeroTokenContractService,
)


@pytest.fixture
def service() -> ZeroTokenContractService:
    return ZeroTokenContractService(estimated_tokens_per_event=150)


@pytest.fixture
def client(
    service: ZeroTokenContractService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(zero_token_contract_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_mirror_event_api(client: TestClient) -> None:
    chat_id = "test-chat-zero-001"
    resp = client.post(
        f"/chats/{chat_id}/zero-token/mirror",
        json={
            "event_id": "evt-101",
            "source": "runtime_sse",
            "event_type": "subagent_status_update",
            "agent_id": "scout-1",
            "payload": {"status": "scanning", "files_checked": 12},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["chat_id"] == chat_id
    assert data["total_events_mirrored"] == 1
    assert data["total_tokens_spent"] == 0  # Zero token guaranteed
    assert data["saved_tokens_estimated"] == 150
    assert data["violations_intercepted"] == 0
    assert data["is_compliant"] is True


def test_mirror_batch_events_api(client: TestClient) -> None:
    chat_id = "test-chat-zero-002"
    resp = client.post(
        f"/chats/{chat_id}/zero-token/mirror-batch",
        json={
            "events": [
                {
                    "event_id": f"batch-{i}",
                    "source": "gateway_webhook",
                    "event_type": "tool_start",
                    "agent_id": "worker-1",
                    "payload": {"step": i},
                }
                for i in range(3)
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_events_mirrored"] == 3
    assert data["total_tokens_spent"] == 0
    assert data["saved_tokens_estimated"] == 450


def test_check_llm_call_non_viz_allowed(client: TestClient) -> None:
    chat_id = "test-chat-zero-003"
    resp = client.post(
        f"/chats/{chat_id}/zero-token/check-llm",
        json={
            "caller_surface": "code_refactor_agent",
            "prompt": "Optimize this Python method",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["allowed"] is True
    assert data["intercepted"] is False
    assert data["reason"] is None


def test_check_llm_call_viz_intercepted(client: TestClient) -> None:
    chat_id = "test-chat-zero-004"
    resp = client.post(
        f"/chats/{chat_id}/zero-token/check-llm",
        json={
            "caller_surface": "fleet_canvas",
            "prompt": "Determine avatar emotions for canvas display",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["allowed"] is False
    assert data["intercepted"] is True
    assert "fleet_canvas" in (data["reason"] or "")


def test_simulate_violation_and_get_audit_api(client: TestClient) -> None:
    chat_id = "test-chat-zero-005"
    # First, mirror 2 events
    client.post(
        f"/chats/{chat_id}/zero-token/mirror",
        json={
            "event_id": "evt-pre-1",
            "source": "runtime_sse",
            "event_type": "subagent_spawned",
            "agent_id": "agent-1",
            "payload": {"role": "planner"},
        },
    )

    # Simulate an illegal viz call to trigger Doctor interception
    sim_resp = client.post(
        f"/chats/{chat_id}/zero-token/simulate-violation",
        json={
            "caller_surface": "3d_office",
            "test_prompt": "Synthesize room ambience description",
        },
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()["data"]
    assert sim_data["intercept_result"]["intercepted"] is True
    assert sim_data["updated_audit"]["violations_intercepted"] == 1
    assert sim_data["updated_audit"]["is_compliant"] is False
    assert sim_data["updated_audit"]["total_tokens_spent"] == 0

    # Query the audit report endpoint
    audit_resp = client.get(f"/chats/{chat_id}/zero-token/audit")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()["data"]
    assert audit_data["total_events_mirrored"] == 1
    assert audit_data["violations_intercepted"] == 1
    assert audit_data["is_compliant"] is False
    assert len(audit_data["recent_violations"]) == 1


def test_reset_audit_api(client: TestClient) -> None:
    chat_id = "test-chat-zero-006"
    client.post(
        f"/chats/{chat_id}/zero-token/mirror",
        json={
            "event_id": "evt-rst",
            "source": "liveness_heartbeat",
            "event_type": "node_heartbeat",
            "agent_id": "node-alpha",
            "payload": {"status": "healthy"},
        },
    )
    reset_resp = client.post(f"/chats/{chat_id}/zero-token/reset")
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()["data"]
    assert reset_data["total_events_mirrored"] == 0
    assert reset_data["is_compliant"] is True
