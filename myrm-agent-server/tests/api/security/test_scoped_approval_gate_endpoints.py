"""
[POS] tests/api/security/test_scoped_approval_gate_endpoints.py
Integration tests for Scoped Approval Grants & Risk-Tiered Gate REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.scoped_approval_gate_router import (
    router as scoped_approval_gate_router,
)
from app.services.security.scoped_approval_gate_service import (
    ScopedApprovalGateService,
    get_scoped_approval_gate_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = ScopedApprovalGateService()
    app = FastAPI()
    app.include_router(scoped_approval_gate_router)
    app.dependency_overrides[get_scoped_approval_gate_service] = lambda: service
    return TestClient(app)


def test_endpoint_issue_grant_and_evaluate(client: TestClient) -> None:
    """Test grant issuance followed by risk evaluation redemption."""
    # 1. Issue grant
    grant_payload = {
        "tool_name": "kubernetes_rollout",
        "scope": "task",
        "agent_id": "deploy-bot",
        "session_id": "sess-k8s",
        "task_id": "task-k8s-99",
    }
    resp_grant = client.post("/scoped-approval-gate/grant", json=grant_payload)
    assert resp_grant.status_code == 200
    grant_data = resp_grant.json()
    assert grant_data["grant_id"].startswith("grant-")
    assert grant_data["scope"] == "task"
    assert grant_data["use_count"] == 0

    # 2. Evaluate with matching grant
    eval_payload = {
        "tool_name": "kubernetes_rollout",
        "risk_tier": "high_risk_write",
        "agent_id": "deploy-bot",
        "session_id": "sess-k8s",
        "task_id": "task-k8s-99",
    }
    resp_eval = client.post("/scoped-approval-gate/evaluate", json=eval_payload)
    assert resp_eval.status_code == 200
    eval_data = resp_eval.json()
    assert eval_data["decision"] == "allow"
    assert eval_data["matched_grant_id"] == grant_data["grant_id"]
    assert eval_data["requires_hitl_prompt"] is False

    # 3. Check active grants
    resp_active = client.get("/scoped-approval-gate/active-grants")
    assert resp_active.status_code == 200
    active_data = resp_active.json()
    assert len(active_data["grants"]) == 1

    # 4. Check audit ledger
    resp_ledger = client.get("/scoped-approval-gate/ledger")
    assert resp_ledger.status_code == 200
    ledger_data = resp_ledger.json()
    assert len(ledger_data["records"]) == 1
    assert ledger_data["records"][0]["tool_name"] == "kubernetes_rollout"


def test_endpoint_risk_tiers_without_grant(client: TestClient) -> None:
    """Test evaluation of read-only and denied tools without grants."""
    # Read-only silent allow
    ro_payload = {
        "tool_name": "read_cluster_pods",
        "risk_tier": "read_only",
        "agent_id": "viewer-bot",
        "session_id": "sess-view",
    }
    resp_ro = client.post("/scoped-approval-gate/evaluate", json=ro_payload)
    assert resp_ro.status_code == 200
    ro_data = resp_ro.json()
    assert ro_data["decision"] == "allow"
    assert ro_data["requires_hitl_prompt"] is False

    # Hard-deny blacklist
    deny_payload = {
        "tool_name": "rm_rf",
        "risk_tier": "high_risk_write",
        "agent_id": "bad-bot",
        "session_id": "sess-bad",
    }
    resp_deny = client.post("/scoped-approval-gate/evaluate", json=deny_payload)
    assert resp_deny.status_code == 200
    deny_data = resp_deny.json()
    assert deny_data["decision"] == "deny"
    assert "blacklist" in deny_data["reason"]


def test_endpoint_revocation_and_metrics(client: TestClient) -> None:
    """Test individual/bulk revocation and telemetry metrics endpoints."""
    # Issue 2 session grants
    g1_resp = client.post(
        "/scoped-approval-gate/grant",
        json={
            "tool_name": "backup_db",
            "scope": "session",
            "agent_id": "maint-bot",
            "session_id": "sess-maint",
        },
    )
    g1_id = g1_resp.json()["grant_id"]

    client.post(
        "/scoped-approval-gate/grant",
        json={
            "tool_name": "restore_db",
            "scope": "session",
            "agent_id": "maint-bot",
            "session_id": "sess-maint",
        },
    )

    # Revoke single
    rev1_resp = client.post(f"/scoped-approval-gate/revoke/{g1_id}")
    assert rev1_resp.status_code == 200
    assert rev1_resp.json()["success"] is True

    # Revoke all
    rev_all_resp = client.post(
        "/scoped-approval-gate/revoke-all",
        json={"session_id": "sess-maint"},
    )
    assert rev_all_resp.status_code == 200
    assert rev_all_resp.json()["revoked_count"] == 1

    # Check metrics
    m_resp = client.get("/scoped-approval-gate/metrics")
    assert m_resp.status_code == 200
    metrics = m_resp.json()
    assert metrics["grants_issued_total"] == 2
    assert metrics["grants_revoked_total"] == 2
