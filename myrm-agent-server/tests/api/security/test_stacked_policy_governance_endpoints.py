"""API endpoint tests for Three-Tier Stacked Policy Governance and Downgrade Gate."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.stacked_policy_governance import (
    DowngradeGateSpec,
)

from app.api.security.stacked_policy_governance_router import (
    router as stacked_policy_governance_router,
)
from app.services.security.stacked_policy_governance_service import (
    StackedPolicyGovernanceService,
    get_stacked_policy_governance_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = StackedPolicyGovernanceService(
        downgrade_spec=DowngradeGateSpec(
            soft_limit_tokens=1000,
            soft_limit_cost=1.0,
            hard_limit_cost=3.0,
            primary_model="claude-3-7-sonnet",
            fallback_model="gpt-4o-mini",
        )
    )
    app = FastAPI()
    app.include_router(
        stacked_policy_governance_router, prefix="/api/v1/security"
    )
    app.dependency_overrides[get_stacked_policy_governance_service] = (
        lambda: test_service
    )
    return TestClient(app)


def test_evaluate_policy_endpoint_server_baseline_and_allow(
    client: TestClient,
) -> None:
    """Test policy evaluation endpoint against server baseline."""
    # 1. Server baseline blocks rm -rf *
    resp_deny = client.post(
        "/api/v1/security/stacked-policies/evaluate",
        json={"phase": "tool_call", "target": "rm -rf *"},
    )
    assert resp_deny.status_code == 200
    deny_data = resp_deny.json()
    assert deny_data["decision"] == "deny"
    assert deny_data["matched_tier"] == "server"

    # 2. Server baseline requires ASK for shell_exec
    resp_ask = client.post(
        "/api/v1/security/stacked-policies/evaluate",
        json={"phase": "tool_call", "target": "shell_exec"},
    )
    assert resp_ask.status_code == 200
    ask_data = resp_ask.json()
    assert ask_data["decision"] == "ask"
    assert ask_data["requires_approval"] is True
    assert ask_data["ask_card"] is not None
    assert "Enterprise Baseline Approval" in ask_data["ask_card"]["prompt_title"]

    # 3. Normal safe operation is allowed
    resp_allow = client.post(
        "/api/v1/security/stacked-policies/evaluate",
        json={"phase": "tool_call", "target": "read_file"},
    )
    assert resp_allow.status_code == 200
    assert resp_allow.json()["decision"] == "allow"


def test_inject_session_rule_and_evaluate(client: TestClient) -> None:
    """Test injecting dynamic session rule and confirming priority short-circuit."""
    # Inject rule
    inject_resp = client.post(
        "/api/v1/security/stacked-policies/inject-session-rule",
        json={
            "session_id": "sess_sandbox_99",
            "name": "deny_all_net",
            "phase": "tool_call",
            "action": "deny",
            "target_pattern": "net_*",
            "reason": "Air-gapped sandbox session denies network fetches",
        },
    )
    assert inject_resp.status_code == 200
    assert inject_resp.json()["status"] == "injected"

    # Evaluate in that session: DENIED at session level
    eval_resp = client.post(
        "/api/v1/security/stacked-policies/evaluate",
        json={
            "phase": "tool_call",
            "target": "net_fetch",
            "session_id": "sess_sandbox_99",
        },
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["decision"] == "deny"
    assert eval_data["matched_tier"] == "session"
    assert eval_data["matched_rule"] == "deny_all_net"

    # In other session: ALLOWED
    other_resp = client.post(
        "/api/v1/security/stacked-policies/evaluate",
        json={
            "phase": "tool_call",
            "target": "net_fetch",
            "session_id": "sess_other_1",
        },
    )
    assert other_resp.status_code == 200
    assert other_resp.json()["decision"] == "allow"


def test_downgrade_gate_tokenomics_endpoint(client: TestClient) -> None:
    """Test recording usage, graceful model downgrade, and status querying via API."""
    # 1. Initial usage below soft threshold
    u1_resp = client.post(
        "/api/v1/security/stacked-policies/record-usage",
        json={
            "session_id": "sess_downgrade_test",
            "additional_tokens": 400,
            "additional_cost": 0.3,
        },
    )
    assert u1_resp.status_code == 200
    d1 = u1_resp.json()
    assert d1["is_downgraded"] is False
    assert d1["active_model"] == "claude-3-7-sonnet"

    # 2. Exceeding soft threshold (tokens reach 1200 >= 1000)
    u2_resp = client.post(
        "/api/v1/security/stacked-policies/record-usage",
        json={
            "session_id": "sess_downgrade_test",
            "additional_tokens": 800,
            "additional_cost": 0.5,
        },
    )
    assert u2_resp.status_code == 200
    d2 = u2_resp.json()
    assert d2["is_downgraded"] is True
    assert d2["is_hard_blocked"] is False
    assert d2["active_model"] == "gpt-4o-mini"
    assert "gracefully downgraded" in d2["message"]

    # 3. Query status via GET endpoint
    status_resp = client.get(
        "/api/v1/security/stacked-policies/downgrade-status",
        params={"session_id": "sess_downgrade_test"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["active_model"] == "gpt-4o-mini"

    # 4. Clear session
    clear_resp = client.post(
        "/api/v1/security/stacked-policies/clear-session",
        params={"session_id": "sess_downgrade_test"},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["status"] == "cleared"
