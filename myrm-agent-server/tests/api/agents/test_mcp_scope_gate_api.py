"""Unit tests for Employee/Agent-Scoped MCP Tool Discovery Gate API endpoints.

[INPUT]
- app.api.agents.mcp_scope_gate_router.router
- app.services.agent.mcp_scope_gate_service.McpScopeGateService
- myrm_agent_harness.agent.sub_agents.mcp_scope_gate.EmployeeScopedMcpDiscoveryGate

[OUTPUT]
- Pytest test cases verifying policy registration, discovery filtering, and invocation authorization

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_mcp_scope_gate_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.mcp_scope_gate import (
    EmployeeScopedMcpDiscoveryGate,
)
from starlette.testclient import TestClient

from app.api.agents.mcp_scope_gate_router import (
    get_mcp_scope_gate_service,
)
from app.api.agents.mcp_scope_gate_router import (
    router as mcp_scope_gate_router,
)
from app.services.agent.mcp_scope_gate_service import McpScopeGateService


@pytest.fixture
def mock_mcp_scope_service() -> McpScopeGateService:
    gate = EmployeeScopedMcpDiscoveryGate()
    return McpScopeGateService(gate=gate)


@pytest.fixture
def mcp_scope_client(
    mock_mcp_scope_service: McpScopeGateService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(mcp_scope_gate_router)
    app.dependency_overrides[get_mcp_scope_gate_service] = lambda: mock_mcp_scope_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_and_get_policy_api(mcp_scope_client: TestClient) -> None:
    agent_id = "agent-developer-01"

    # 1. Register policy
    policy_payload = {
        "agent_id": agent_id,
        "allowed_mcp_servers": ["github", "gitlab"],
        "tool_allowlist_map": {"github": ["create_pr", "list_issues"]},
        "strict_mode": True,
        "updated_at": "2026-08-20T12:00:00Z",
    }
    post_resp = mcp_scope_client.post(
        f"/agents/{agent_id}/mcp-scope/policy", json=policy_payload
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["code"] == 0
    data = post_resp.json()["data"]
    assert data["agent_id"] == agent_id
    assert data["allowed_mcp_servers"] == ["github", "gitlab"]

    # 2. Get policy
    get_resp = mcp_scope_client.get(f"/agents/{agent_id}/mcp-scope/policy")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["agent_id"] == agent_id
    assert get_data["tool_allowlist_map"] == {"github": ["create_pr", "list_issues"]}


def test_filter_discovered_tools_api(mcp_scope_client: TestClient) -> None:
    agent_id = "agent-support-02"

    # Pre-register policy
    policy_payload = {
        "agent_id": agent_id,
        "allowed_mcp_servers": ["zendesk"],
        "tool_allowlist_map": {"zendesk": ["read_ticket"]},
        "strict_mode": True,
        "updated_at": "",
    }
    mcp_scope_client.post(f"/agents/{agent_id}/mcp-scope/policy", json=policy_payload)

    # Filter candidates
    filter_payload = {
        "candidates": [
            {"server_name": "zendesk", "tool_name": "read_ticket", "description": "Read ticket details"},
            {"server_name": "zendesk", "tool_name": "delete_ticket", "description": "Dangerous delete"},
            {"server_name": "aws", "tool_name": "reboot_instance", "description": "AWS reboot"},
        ]
    }
    resp = mcp_scope_client.post(
        f"/agents/{agent_id}/mcp-scope/filter-discovered", json=filter_payload
    )
    assert resp.status_code == 200
    verdict = resp.json()["data"]
    assert verdict["total_discovered"] == 3
    assert verdict["allowed_count"] == 1
    assert verdict["blocked_count"] == 2
    assert verdict["allowed_tools"][0]["tool_name"] == "read_ticket"
    blocked_names = {t["tool_name"] for t in verdict["blocked_tools"]}
    assert blocked_names == {"delete_ticket", "reboot_instance"}


def test_verify_tool_call_api(mcp_scope_client: TestClient) -> None:
    agent_id = "agent-readonly-03"

    # Register policy
    policy_payload = {
        "agent_id": agent_id,
        "allowed_mcp_servers": ["sqlite"],
        "tool_allowlist_map": {"sqlite": ["select_query"]},
        "strict_mode": True,
        "updated_at": "",
    }
    mcp_scope_client.post(f"/agents/{agent_id}/mcp-scope/policy", json=policy_payload)

    # 1. Allowed call
    ok_resp = mcp_scope_client.post(
        f"/agents/{agent_id}/mcp-scope/verify-call",
        json={"server_name": "sqlite", "tool_name": "select_query"},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["is_allowed"] is True

    # 2. Blocked tool call -> 403 Forbidden
    blocked_resp = mcp_scope_client.post(
        f"/agents/{agent_id}/mcp-scope/verify-call",
        json={"server_name": "sqlite", "tool_name": "drop_table"},
    )
    assert blocked_resp.status_code == 403
