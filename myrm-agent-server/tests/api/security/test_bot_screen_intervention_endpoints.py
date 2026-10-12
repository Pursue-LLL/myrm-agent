"""
Integration tests for Bot Screen Auditable Operational Control & Intervention Evidence REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.bot_screen_intervention_router import (
    router as bot_screen_intervention_router,
)
from app.services.security.bot_screen_intervention_service import (
    BotScreenInterventionService,
    get_bot_screen_intervention_service,
)


@pytest.fixture
def client() -> TestClient:
    service = BotScreenInterventionService()
    app = FastAPI()
    app.include_router(bot_screen_intervention_router)
    app.dependency_overrides[get_bot_screen_intervention_service] = lambda: service
    return TestClient(app)


def test_endpoint_classify_element_risk(client: TestClient) -> None:
    resp = client.post(
        "/bot-screen-intervention/classify-element-risk",
        json={
            "selector": "#wire-transfer-action",
            "label": "Execute Bank Wire",
            "action_type": "click",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_tier"] == "HIGH_RISK_FINANCIAL"
    assert data["selector"] == "#wire-transfer-action"


def test_endpoint_evaluate_action(client: TestClient) -> None:
    resp = client.post(
        "/bot-screen-intervention/evaluate-action",
        json={
            "action_id": "act-transfer-1",
            "target_selector": "#wire-transfer-action",
            "action_type": "click",
            "label": "Execute Bank Wire",
            "value_masked": "",
            "risk_tier": "HIGH_RISK_FINANCIAL",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_id"] == "act-transfer-1"
    assert data["decision"] == "PENDING_HUMAN_APPROVAL"
    assert "checkpoint approval" in data["reason"]


def test_endpoint_intervention_lifecycle(client: TestClient) -> None:
    # 1. Start takeover
    start_resp = client.post(
        "/bot-screen-intervention/interventions/start",
        json={
            "session_id": "session-fin-101",
            "operator_id": "auditor_dave",
            "before_snapshot_hash": "sha_snapshot_before_123",
        },
    )
    assert start_resp.status_code == 200
    intervene_id = start_resp.json()["intervention_id"]
    assert intervene_id.startswith("intervene-")

    # 2. Record event
    rec_resp = client.post(
        "/bot-screen-intervention/interventions/record-event",
        json={
            "intervention_id": intervene_id,
            "event_type": "keyboard_input",
            "target_selector": "#auth-token-input",
            "raw_data": "secret_2fa_token",
        },
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["data_sanitized"] == "[REDACTED_SENSITIVE_CREDENTIAL]"

    # 3. Seal bundle
    seal_resp = client.post(
        "/bot-screen-intervention/interventions/seal",
        json={
            "intervention_id": intervene_id,
            "after_snapshot_hash": "sha_snapshot_after_456",
        },
    )
    assert seal_resp.status_code == 200
    bundle_data = seal_resp.json()
    assert bundle_data["intervention_id"] == intervene_id
    assert bundle_data["event_count"] == 1
    assert bundle_data["is_tamper_evident"]
    assert len(bundle_data["bundle_sha256"]) == 64

    # 4. Get bundle by ID
    get_resp = client.get(f"/bot-screen-intervention/interventions/{intervene_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["bundle_sha256"] == bundle_data["bundle_sha256"]

    # 5. Non-existent bundle returns 404
    missing_resp = client.get("/bot-screen-intervention/interventions/non-existent-id")
    assert missing_resp.status_code == 404


def test_endpoint_verify_assertion_and_metrics(client: TestClient) -> None:
    # Verify assertion
    assert_resp = client.post(
        "/bot-screen-intervention/assertions/verify",
        json={
            "probe_id": "probe-ui-99",
            "expected_selector": "#banner-success",
            "expected_text_contains": "Transferred",
            "actual_text": "Funds successfully Transferred.",
            "visual_hash_match": True,
        },
    )
    assert assert_resp.status_code == 200
    assert assert_resp.json()["passed"]

    # Retrieve metrics
    metrics_resp = client.get("/bot-screen-intervention/metrics")
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert "total_screen_actions" in m
    assert "approval_checkpoints_triggered" in m
    assert "manual_takeovers_conducted" in m
    assert "assertion_failures" in m
    assert "evidence_bundles_sealed" in m
