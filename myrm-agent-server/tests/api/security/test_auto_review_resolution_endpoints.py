"""
[POS] tests/api/security/test_auto_review_resolution_endpoints.py
[INPUT] app.api.security.auto_review_resolution_router, app.services.security.auto_review_resolution_service
[OUTPUT] endpoint tests

API endpoint tests for Auto-Review Denial Four-Way Adaptive Resolution State Machine Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.auto_review_resolution_router import (
    router as auto_review_resolution_router,
)
from app.services.security.auto_review_resolution_service import (
    AutoReviewResolutionService,
    get_auto_review_resolution_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = AutoReviewResolutionService()
    app = FastAPI()
    app.include_router(auto_review_resolution_router)
    app.dependency_overrides[get_auto_review_resolution_service] = (
        lambda: test_service
    )
    return TestClient(app)


def test_report_and_get_denial_endpoints(client: TestClient) -> None:
    """Test POST /auto-review-resolution/report-denial and GET /active-denial/{session_id}."""
    session_id = "sess-api-diag-01"
    req_payload = {
        "session_id": session_id,
        "blocked_action": "rm_rf_root",
        "denial_reason": "Destructive filesystem modification blocked by security boundary.",
        "reason_code": "HIGH_RISK_ACTION",
        "policy_rule_id": "RULE-SEC-FS-01",
        "context_data": {"path": "/"},
    }

    # 1. Report denial
    report_res = client.post("/auto-review-resolution/report-denial", json=req_payload)
    assert report_res.status_code == 200
    diag = report_res.json()
    assert diag["blocked_action"] == "rm_rf_root"
    assert diag["reason_code"] == "HIGH_RISK_ACTION"
    assert diag["suggested_branch"] == "HANDOVER_TO_USER"
    diag_id = diag["diagnostic_id"]

    # 2. Get active denial
    get_res = client.get(f"/auto-review-resolution/active-denial/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["diagnostic_id"] == diag_id


def test_evaluate_branch_and_commit_endpoints(client: TestClient) -> None:
    """Test POST /auto-review-resolution/evaluate-branch and POST /commit-resolution."""
    session_id = "sess-api-branch-01"

    # Report denial first
    client.post(
        "/auto-review-resolution/report-denial",
        json={
            "session_id": session_id,
            "blocked_action": "shell_net_dial",
            "denial_reason": "Outbound raw socket forbidden.",
            "reason_code": "POLICY_VIOLATION",
            "policy_rule_id": "RULE-NET-01",
        },
    )

    # Evaluate branch
    eval_res = client.post(
        "/auto-review-resolution/evaluate-branch",
        json={"session_id": session_id, "proposed_branch": "TRY_ALTERNATIVE"},
    )
    assert eval_res.status_code == 200
    e_data = eval_res.json()
    assert e_data["effective_branch"] == "TRY_ALTERNATIVE"
    assert e_data["loop_breaker_triggered"] is False

    # Commit decision
    commit_res = client.post(
        "/auto-review-resolution/commit-resolution",
        json={
            "session_id": session_id,
            "chosen_branch": "TRY_ALTERNATIVE",
            "rationale": "Attempting approved HTTP proxy alternative.",
            "alternative_attempted": "http_proxy_get",
        },
    )
    assert commit_res.status_code == 200
    assert commit_res.json()["chosen_branch"] == "TRY_ALTERNATIVE"

    # Verify history
    hist_res = client.get(f"/auto-review-resolution/history/{session_id}")
    assert hist_res.status_code == 200
    assert len(hist_res.json()) == 1


def test_handover_deck_and_metrics_endpoints(client: TestClient) -> None:
    """Test POST /auto-review-resolution/handover, execution, dismissal, and metrics."""
    session_id = "sess-api-handover"

    # 1. Stage handover card
    stage_payload = {
        "session_id": session_id,
        "task_description": "Merge release commit into protected branch",
        "prepared_command": "git push upstream release-2.0",
        "parameters": {"branch": "release-2.0"},
        "guidance_notes": "Please review release notes before executing.",
    }
    create_res = client.post("/auto-review-resolution/handover", json=stage_payload)
    assert create_res.status_code == 201
    deck = create_res.json()
    handover_id = deck["handover_id"]
    assert deck["status"] == "STAGED"

    # 2. Get card by ID
    get_deck = client.get(f"/auto-review-resolution/handover/{handover_id}")
    assert get_deck.status_code == 200
    assert get_deck.json()["handover_id"] == handover_id

    # 3. List staged cards
    list_decks = client.get(f"/auto-review-resolution/handovers?session_id={session_id}")
    assert list_decks.status_code == 200
    assert any(d["handover_id"] == handover_id for d in list_decks.json())

    # 4. User executes card
    exec_res = client.post(f"/auto-review-resolution/handover/{handover_id}/execute")
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "EXECUTED_BY_USER"
    assert exec_res.json()["executed_at"] is not None

    # 5. Metrics
    metrics_res = client.get("/auto-review-resolution/metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert m_data["handovers_executed_by_user"] >= 1
