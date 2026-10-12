"""API endpoint tests for Action Grants and Trust Budget Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.action_grant_router import router as action_grant_router
from app.services.security.action_grant_service import (
    ActionGrantService,
    get_action_grant_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ActionGrantService(suggestion_threshold=2)
    app = FastAPI()
    app.include_router(action_grant_router, prefix="/api/v1/security")
    app.dependency_overrides[get_action_grant_service] = lambda: test_service
    return TestClient(app)


def test_grant_create_and_evaluate_endpoints(client: TestClient) -> None:
    """Test creating a grant and evaluating matching action via REST API."""
    # 1. Create grant
    create_resp = client.post(
        "/api/v1/security/grants/create",
        json={
            "agent_id": "agent-finance-bot",
            "service": "stripe",
            "action": "refund",
            "transaction": "tx_order_1001",
            "ttl_seconds": 600,
            "max_uses": 1,
        },
    )
    assert create_resp.status_code == 200
    grant_data = create_resp.json()
    grant_id = grant_data["grant_id"]
    assert grant_id.startswith("grant_")
    assert grant_data["agent_id"] == "agent-finance-bot"
    assert grant_data["used_count"] == 0

    # 2. Evaluate matching action
    eval_resp = client.post(
        "/api/v1/security/grants/evaluate",
        json={
            "agent_id": "agent-finance-bot",
            "service": "stripe",
            "action": "refund",
            "transaction": "tx_order_1001",
        },
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["is_granted"] is True
    assert eval_data["status"] == "granted"
    assert eval_data["grant_id"] == grant_id

    # 3. Impersonation attempt by another agent is rejected
    impersonate_resp = client.post(
        "/api/v1/security/grants/evaluate",
        json={
            "agent_id": "agent-rogue",
            "service": "stripe",
            "action": "refund",
            "transaction": "tx_order_1001",
        },
    )
    assert impersonate_resp.status_code == 200
    imp_data = impersonate_resp.json()
    assert imp_data["is_granted"] is False
    assert imp_data["status"] == "not_found"


def test_list_active_and_revoke_endpoints(client: TestClient) -> None:
    """Test listing active grants and revoking grants."""
    # Create two grants
    c1 = client.post(
        "/api/v1/security/grants/create",
        json={
            "agent_id": "agent-1",
            "service": "slack",
            "action": "send",
            "transaction": "*",
            "ttl_seconds": 300,
        },
    )
    g1_id = c1.json()["grant_id"]

    client.post(
        "/api/v1/security/grants/create",
        json={
            "agent_id": "agent-2",
            "service": "github",
            "action": "push",
            "transaction": "main",
            "ttl_seconds": 300,
        },
    )

    # List active grants filtered by agent
    list_resp = client.get("/api/v1/security/grants/active?agent_id=agent-1")
    assert list_resp.status_code == 200
    grants = list_resp.json()
    assert len(grants) == 1
    assert grants[0]["grant_id"] == g1_id

    # Revoke grant g1
    rev_resp = client.post(
        "/api/v1/security/grants/revoke",
        json={"grant_id": g1_id, "reason": "User revoked access"},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["success"] is True

    # Duplicate revoke returns 404
    rev_dup = client.post(
        "/api/v1/security/grants/revoke",
        json={"grant_id": g1_id},
    )
    assert rev_dup.status_code == 404


def test_cascade_reclaim_endpoint(client: TestClient) -> None:
    """Test cascade reclaim endpoint by service connector."""
    client.post(
        "/api/v1/security/grants/create",
        json={
            "agent_id": "agent-a",
            "service": "zendesk",
            "action": "reply",
            "transaction": "ticket_1",
            "ttl_seconds": 300,
        },
    )
    client.post(
        "/api/v1/security/grants/create",
        json={
            "agent_id": "agent-b",
            "service": "zendesk",
            "action": "close",
            "transaction": "ticket_2",
            "ttl_seconds": 300,
        },
    )

    reclaim_resp = client.post(
        "/api/v1/security/grants/cascade-reclaim",
        json={"service": "zendesk", "reason": "Zendesk API Token expired"},
    )
    assert reclaim_resp.status_code == 200
    assert reclaim_resp.json()["revoked_count"] == 2


def test_trust_budget_endpoints(client: TestClient) -> None:
    """Test querying budget, recording approval, and demotion via API."""
    # 1. Record first approval
    app1_resp = client.post(
        "/api/v1/security/grants/record-approval",
        json={"agent_id": "agent-mail", "service": "gmail", "action": "send"},
    )
    assert app1_resp.status_code == 200
    d1 = app1_resp.json()
    assert d1["consecutive_approvals"] == 1
    assert d1["should_suggest_grant"] is False

    # 2. Record second approval (reaches suggestion threshold 2)
    app2_resp = client.post(
        "/api/v1/security/grants/record-approval",
        json={"agent_id": "agent-mail", "service": "gmail", "action": "send"},
    )
    assert app2_resp.status_code == 200
    d2 = app2_resp.json()
    assert d2["consecutive_approvals"] == 2
    assert d2["should_suggest_grant"] is True

    # 3. Record demotion
    demote_resp = client.post(
        "/api/v1/security/grants/record-demotion",
        json={
            "agent_id": "agent-mail",
            "service": "gmail",
            "action": "send",
            "reason": "Email body contained incorrect recipient",
        },
    )
    assert demote_resp.status_code == 200
    demote_data = demote_resp.json()
    assert demote_data["consecutive_approvals"] == 0
    assert demote_data["is_locked_to_ask"] is True
    assert demote_data["should_suggest_grant"] is False
