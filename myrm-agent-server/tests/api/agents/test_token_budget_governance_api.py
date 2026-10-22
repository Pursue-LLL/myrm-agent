"""Unit tests for One-Model Multi-Agent Shared Context Token Budget Governance API (Item 52).

[INPUT]
- app.api.agents.token_budget_governance_router.router
- app.services.agent.token_budget_governance_service.TokenBudgetGovernanceService

[OUTPUT]
- Pytest test cases validating role budget declarations, fan-out prechecks,
  consumption ledger logging, snapshot querying, and Doctor Nudge warnings.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_token_budget_governance_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.token_budget_governance_router import (
    get_service,
)
from app.api.agents.token_budget_governance_router import (
    router as token_budget_governance_router,
)
from app.services.agent.token_budget_governance_service import (
    TokenBudgetGovernanceService,
)


@pytest.fixture
def service() -> TokenBudgetGovernanceService:
    return TokenBudgetGovernanceService()


@pytest.fixture
def client(
    service: TokenBudgetGovernanceService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(token_budget_governance_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_role_budget_api(client: TestClient) -> None:
    chat_id = "test-gov-001"

    resp = client.post(
        f"/chats/{chat_id}/token-governance/roles",
        json={
            "role_name": "architect",
            "token_ceiling": 20000,
            "stop_condition": "halt_and_report",
            "allow_overflow": False,
        },
    )
    assert resp.status_code == 201
    spec = resp.json()["data"]
    assert spec["role_name"] == "architect"
    assert spec["token_ceiling"] == 20000
    assert spec["stop_condition"] == "halt_and_report"


def test_precheck_fanout_api(client: TestClient) -> None:
    chat_id = "test-gov-002"

    # Register role with 5,000 ceiling
    client.post(
        f"/chats/{chat_id}/token-governance/roles",
        json={
            "role_name": "researcher",
            "token_ceiling": 5000,
            "stop_condition": "halt_and_report",
            "allow_overflow": False,
        },
    )

    # Precheck within budget
    pass_resp = client.post(
        f"/chats/{chat_id}/token-governance/precheck",
        json={"role_name": "researcher", "estimated_tokens": 2000},
    )
    assert pass_resp.status_code == 200
    res_pass = pass_resp.json()["data"]
    assert res_pass["passed"] is True

    # Precheck exceeding role ceiling
    fail_resp = client.post(
        f"/chats/{chat_id}/token-governance/precheck",
        json={"role_name": "researcher", "estimated_tokens": 6000},
    )
    assert fail_resp.status_code == 200
    res_fail = fail_resp.json()["data"]
    assert res_fail["passed"] is False
    assert "Per-role ceiling exceeded" in res_fail["reason"]


def test_record_consumption_and_snapshot_api(client: TestClient) -> None:
    chat_id = "test-gov-003"

    # 1. Routing overhead turn
    r1 = client.post(
        f"/chats/{chat_id}/token-governance/consumption",
        json={
            "agent_role": "router",
            "category": "routing_overhead",
            "prompt_tokens": 500,
            "completion_tokens": 100,
        },
    )
    assert r1.status_code == 200

    # 2. Execution payload turn
    r2 = client.post(
        f"/chats/{chat_id}/token-governance/consumption",
        json={
            "agent_role": "coder",
            "category": "execution_payload",
            "prompt_tokens": 2000,
            "completion_tokens": 400,
        },
    )
    assert r2.status_code == 200

    # Query snapshot
    snap_resp = client.get(f"/chats/{chat_id}/token-governance/snapshot")
    assert snap_resp.status_code == 200
    snap = snap_resp.json()["data"]
    assert snap["session_id"] == chat_id
    assert snap["total_tokens_spent"] == 3000
    assert snap["routing_tokens_spent"] == 600
    assert snap["execution_tokens_spent"] == 2400
    assert snap["routing_ratio"] == 0.2
    assert snap["role_usage"]["router"] == 600
    assert snap["role_usage"]["coder"] == 2400


def test_doctor_nudges_alerts_api(client: TestClient) -> None:
    chat_id = "test-gov-004"

    # Burn tokens with excessive routing ratio: 1,500 routing + 1,000 execution -> 60% > 35%
    client.post(
        f"/chats/{chat_id}/token-governance/consumption",
        json={
            "agent_role": "router",
            "category": "routing_overhead",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )
    client.post(
        f"/chats/{chat_id}/token-governance/consumption",
        json={
            "agent_role": "worker",
            "category": "execution_payload",
            "prompt_tokens": 600,
            "completion_tokens": 400,
        },
    )

    alert_resp = client.get(f"/chats/{chat_id}/token-governance/doctor-nudges")
    assert alert_resp.status_code == 200
    alerts = alert_resp.json()["data"]
    assert len(alerts) >= 1
    assert any("Routing overhead is 60.0%" in a["message"] for a in alerts)


def test_reset_token_governance_api(client: TestClient) -> None:
    chat_id = "test-gov-005"

    client.post(
        f"/chats/{chat_id}/token-governance/consumption",
        json={
            "agent_role": "bot",
            "category": "execution_payload",
            "prompt_tokens": 300,
            "completion_tokens": 200,
        },
    )

    reset_resp = client.post(f"/chats/{chat_id}/token-governance/reset")
    assert reset_resp.status_code == 200

    new_snap = client.get(f"/chats/{chat_id}/token-governance/snapshot").json()["data"]
    assert new_snap["total_tokens_spent"] == 0
