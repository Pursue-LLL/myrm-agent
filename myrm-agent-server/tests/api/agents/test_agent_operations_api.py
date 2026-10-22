"""Unit tests for Agent-Owned multi-agent operations fabric API endpoints.

[INPUT]
- app.api.agents.agent_operations_router.router
- app.services.agent.agent_operations_service.AgentOperationsService

[OUTPUT]
- Pytest test cases verifying agent registration, list-form roster querying, capability resolution, and isolated error stacks.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_agent_operations_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.agent_operations_router import (
    get_agent_operations_service,
)
from app.api.agents.agent_operations_router import (
    router as agent_operations_router,
)
from app.services.agent.agent_operations_service import AgentOperationsService


@pytest.fixture
def mock_agent_ops_service() -> AgentOperationsService:
    return AgentOperationsService()


@pytest.fixture
def agent_ops_client(
    mock_agent_ops_service: AgentOperationsService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(agent_operations_router)
    app.dependency_overrides[get_agent_operations_service] = lambda: mock_agent_ops_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_and_roster_flow(agent_ops_client: TestClient) -> None:
    # 1. Register agent coder
    reg_payload = {
        "agent_id": "worker_coder",
        "role": "code_implementer",
        "session_id": "session_test_01",
        "provider_config": {
            "provider_name": "deepseek",
            "model_name": "deepseek-coder",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout_seconds": 60.0,
        },
        "capabilities": ["write_code", "format_code"],
        "allowlist": ["tool_fs_write", "tool_format"],
    }
    resp = agent_ops_client.post("/agents/operations/register", json=reg_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["agent_id"] == "worker_coder"
    assert data["provider_model"] == "deepseek/deepseek-coder"
    assert data["is_healthy"] is True

    # 2. Get list-form roster
    resp_roster = agent_ops_client.get("/agents/operations/roster?session_id=session_test_01")
    assert resp_roster.status_code == 200
    roster_data = resp_roster.json()["data"]
    assert roster_data["total_count"] == 1
    assert roster_data["agents"][0]["agent_id"] == "worker_coder"


def test_resolve_capability_flow(agent_ops_client: TestClient) -> None:
    # Register an agent with specific allowlist
    reg_payload = {
        "agent_id": "worker_reviewer",
        "role": "code_reviewer",
        "session_id": "session_test_02",
        "provider_config": {
            "provider_name": "anthropic",
            "model_name": "claude-3-5-sonnet",
            "temperature": 0.4,
            "timeout_seconds": 30.0,
        },
        "capabilities": ["review_code"],
        "allowlist": ["tool_read_diff", "tool_post_comment"],
    }
    agent_ops_client.post("/agents/operations/register", json=reg_payload)

    # Allowed capability
    resp_allowed = agent_ops_client.post(
        "/agents/operations/worker_reviewer/resolve-capability?session_id=session_test_02",
        json={"target_capability": "tool_read_diff"},
    )
    assert resp_allowed.status_code == 200
    assert resp_allowed.json()["data"]["is_allowed"] is True

    # Disallowed capability
    resp_denied = agent_ops_client.post(
        "/agents/operations/worker_reviewer/resolve-capability?session_id=session_test_02",
        json={"target_capability": "tool_execute_shell"},
    )
    assert resp_denied.status_code == 200
    assert resp_denied.json()["data"]["is_allowed"] is False


def test_isolated_error_stack_flow(agent_ops_client: TestClient) -> None:
    # Register agent
    reg_payload = {
        "agent_id": "worker_runner",
        "role": "test_runner",
        "session_id": "session_test_03",
        "provider_config": {
            "provider_name": "openai",
            "model_name": "gpt-4o",
            "temperature": 0.0,
            "timeout_seconds": 45.0,
        },
        "capabilities": ["run_tests"],
        "allowlist": ["*"],
    }
    agent_ops_client.post("/agents/operations/register", json=reg_payload)

    # 1. Record error
    err_payload = {
        "operation": "execute_test_suite",
        "error_type": "AssertionError",
        "message": "Expected 200 OK but received 500 Internal Server Error",
        "fatal": True,
        "context": {"suite": "integration_tests"},
    }
    resp_record = agent_ops_client.post(
        "/agents/operations/worker_runner/record-error?session_id=session_test_03",
        json=err_payload,
    )
    assert resp_record.status_code == 200
    err_data = resp_record.json()["data"]
    assert err_data["error_type"] == "AssertionError"
    assert err_data["fatal"] is True

    # 2. Fetch error stack
    resp_errors = agent_ops_client.get(
        "/agents/operations/worker_runner/errors?session_id=session_test_03",
    )
    assert resp_errors.status_code == 200
    errors_list = resp_errors.json()["data"]
    assert len(errors_list) == 1
    assert errors_list[0]["operation"] == "execute_test_suite"

    # 3. Check roster health degradation
    resp_roster = agent_ops_client.get("/agents/operations/roster?session_id=session_test_03")
    assert resp_roster.status_code == 200
    agent_entry = resp_roster.json()["data"]["agents"][0]
    assert agent_entry["is_healthy"] is False
    assert agent_entry["error_count"] == 1

    # 4. Clear error stack
    resp_clear = agent_ops_client.delete(
        "/agents/operations/worker_runner/errors?session_id=session_test_03",
    )
    assert resp_clear.status_code == 200
    assert resp_clear.json()["data"]["cleared"] is True

    # Check that error stack is now empty
    resp_errors_after = agent_ops_client.get(
        "/agents/operations/worker_runner/errors?session_id=session_test_03",
    )
    assert resp_errors_after.status_code == 200
    assert len(resp_errors_after.json()["data"]) == 0
