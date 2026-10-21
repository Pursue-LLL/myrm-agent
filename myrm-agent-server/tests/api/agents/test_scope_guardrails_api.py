"""Unit tests for Orchestrator Scope Guardrails and Safe Team Design Mode API endpoints (Item 37).

[INPUT]
- app.api.agents.scope_guardrails_router.router
- app.services.agent.scope_guardrails_service.ScopeGuardrailsService

[OUTPUT]
- Pytest cases verifying team scope audit, forbidden tool blocking, least-privilege pruning,
  fan-out caps, and session configuration management.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_scope_guardrails_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.scope_guardrails_router import (
    get_scope_guardrails_service,
)
from app.api.agents.scope_guardrails_router import (
    router as scope_guardrails_router,
)
from app.schemas.scope_guardrails import (
    ViolationSeverityEnum,
    ViolationTypeEnum,
)
from app.services.agent.scope_guardrails_service import (
    ScopeGuardrailsService,
)


@pytest.fixture
def guardrails_service() -> ScopeGuardrailsService:
    service = ScopeGuardrailsService()
    service.clear_all()
    return service


@pytest.fixture
def guardrails_client(
    guardrails_service: ScopeGuardrailsService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(scope_guardrails_router)
    app.dependency_overrides[get_scope_guardrails_service] = lambda: guardrails_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_audit_safe_team_scope(guardrails_client: TestClient) -> None:
    chat_id = "chat_guardrails_01"

    resp = guardrails_client.post(
        f"/chats/{chat_id}/scope-guardrails/audit",
        json={
            "candidates": [
                {
                    "role_key": "orchestrator",
                    "display_name": "Lead",
                    "requested_tools": ["spawn_subagent", "delegate_task"],
                },
                {
                    "role_key": "coder",
                    "display_name": "Coder",
                    "requested_tools": ["file_read", "file_write", "test_runner"],
                },
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_safe"] is True
    assert data["fanout_capped"] is False
    assert data["original_member_count"] == 2
    assert data["approved_member_count"] == 2
    assert len(data["violations"]) == 0
    assert "coder" in data["sanitized_tools_map"]
    assert data["sanitized_tools_map"]["coder"] == ["file_read", "file_write", "test_runner"]


def test_audit_forbidden_tool_and_role_pruning(guardrails_client: TestClient) -> None:
    chat_id = "chat_guardrails_02"

    resp = guardrails_client.post(
        f"/chats/{chat_id}/scope-guardrails/audit",
        json={
            "candidates": [
                {
                    "role_key": "researcher",
                    "display_name": "Scout",
                    # researcher requested raw_bash_root (forbidden) and file_write (exceeds allowlist)
                    "requested_tools": ["web_search", "file_write", "raw_bash_root"],
                }
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_safe"] is False
    assert len(data["violations"]) == 2

    # High risk raw_bash_root is a BLOCKER
    blockers = [v for v in data["violations"] if v["severity"] == ViolationSeverityEnum.BLOCKER.value]
    assert len(blockers) == 1
    assert blockers[0]["violation_type"] == ViolationTypeEnum.FORBIDDEN_TOOL.value
    assert blockers[0]["tool_name"] == "raw_bash_root"

    # Excess file_write is a WARNING
    warnings = [v for v in data["violations"] if v["severity"] == ViolationSeverityEnum.WARNING.value]
    assert len(warnings) == 1
    assert warnings[0]["violation_type"] == ViolationTypeEnum.ROLE_SCOPE_EXCEEDED.value
    assert warnings[0]["tool_name"] == "file_write"

    # Sanitized tools should only keep legal tools
    assert data["sanitized_tools_map"]["researcher"] == ["web_search"]


def test_audit_fanout_cap_enforcement(guardrails_client: TestClient) -> None:
    chat_id = "chat_guardrails_03"

    candidates = [
        {"role_key": "coder", "display_name": f"Worker {i}", "requested_tools": ["file_read"]}
        for i in range(8)
    ]

    resp = guardrails_client.post(
        f"/chats/{chat_id}/scope-guardrails/audit",
        json={"candidates": candidates},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["fanout_capped"] is True
    assert data["is_safe"] is False
    assert data["original_member_count"] == 8
    assert data["approved_member_count"] == 5
    assert any(v["violation_type"] == ViolationTypeEnum.FANOUT_LIMIT_EXCEEDED.value for v in data["violations"])


def test_session_configuration_lifecycle(guardrails_client: TestClient) -> None:
    chat_id = "chat_guardrails_04"

    # 1. Get default config
    get_resp = guardrails_client.get(f"/chats/{chat_id}/scope-guardrails/config")
    assert get_resp.status_code == 200
    cfg = get_resp.json()["data"]
    assert cfg["max_fanout_cap"] == 5

    # 2. Update session config
    put_resp = guardrails_client.put(
        f"/chats/{chat_id}/scope-guardrails/config",
        json={
            "max_fanout_cap": 3,
            "require_hitl_for_high_risk": True,
            "forbidden_tools": ["danger_tool_x"],
            "role_tool_allowlists": {"custom_worker": ["tool_1", "tool_2"]},
        },
    )
    assert put_resp.status_code == 200
    updated_cfg = put_resp.json()["data"]
    assert updated_cfg["max_fanout_cap"] == 3
    assert "danger_tool_x" in updated_cfg["forbidden_tools"]

    # 3. Reset config
    del_resp = guardrails_client.delete(f"/chats/{chat_id}/scope-guardrails/config")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["reset"] is True

    # 4. Verify reverted to default 5
    get_after = guardrails_client.get(f"/chats/{chat_id}/scope-guardrails/config")
    assert get_after.json()["data"]["max_fanout_cap"] == 5
