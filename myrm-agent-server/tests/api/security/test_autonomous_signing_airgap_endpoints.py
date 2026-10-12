"""
[POS] tests/api/security/test_autonomous_signing_airgap_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.autonomous_signing_airgap_router
[OUTPUT] Integration tests for Autonomous Signing Airgap REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.autonomous_signing_airgap_router import (
    router as autonomous_signing_airgap_router,
)
from app.services.security.autonomous_signing_airgap_service import (
    AutonomousSigningAirgapService,
    get_autonomous_signing_airgap_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = AutonomousSigningAirgapService()
    app = FastAPI()
    app.include_router(autonomous_signing_airgap_router)
    app.dependency_overrides[get_autonomous_signing_airgap_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_and_step_up(client: TestClient) -> None:
    """Test evaluation endpoint for silent authorization and step-up escalation workflow."""
    # 1. Update quota config
    cfg_resp = client.put(
        "/autonomous-signing-airgap/quota",
        json={
            "single_tx_limit": 100.0,
            "daily_cumulative_limit": 500.0,
            "trusted_recipients": ["0xWhitelistedContract"],
        },
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["single_tx_limit"] == 100.0

    # 2. Silent authorized transaction
    eval_resp = client.post(
        "/autonomous-signing-airgap/evaluate",
        json={
            "tx_id": "api-tx-01",
            "recipient": "0xWhitelistedContract",
            "amount": 30.0,
            "currency": "USDC",
            "chain_or_network": "base",
            "call_data_summary": "swap()",
        },
    )
    assert eval_resp.status_code == 200
    v1 = eval_resp.json()
    assert v1["decision"] == "SILENT_AUTHORIZED"
    assert v1["is_approved_to_sign"] is True
    assert v1["signature_token"] is not None

    # 3. Step-up triggered transaction (> 100, <= 300)
    stepup_resp = client.post(
        "/autonomous-signing-airgap/evaluate",
        json={
            "tx_id": "api-tx-02",
            "recipient": "0xWhitelistedContract",
            "amount": 160.0,
            "currency": "USDC",
            "chain_or_network": "base",
        },
    )
    assert stepup_resp.status_code == 200
    v2 = stepup_resp.json()
    assert v2["decision"] == "REQUIRE_HITL_STEP_UP"
    assert v2["is_approved_to_sign"] is False

    # 4. Pending list check
    pending_resp = client.get("/autonomous-signing-airgap/step-up/pending")
    assert pending_resp.status_code == 200
    items = pending_resp.json()
    assert len(items) == 1
    assert items[0]["tx_id"] == "api-tx-02"

    # 5. Approve stepped-up transaction
    appr_resp = client.post(
        "/autonomous-signing-airgap/step-up/approve",
        json={
            "tx_id": "api-tx-02",
            "approver_note": "Admin approved payout",
        },
    )
    assert appr_resp.status_code == 200
    v3 = appr_resp.json()
    assert v3["decision"] == "SILENT_AUTHORIZED"
    assert v3["is_approved_to_sign"] is True
    assert v3["signature_token"] is not None


def test_endpoint_step_up_reject(client: TestClient) -> None:
    """Test rejection and missing handling for stepped-up transactions."""
    client.put(
        "/autonomous-signing-airgap/quota",
        json={
            "single_tx_limit": 50.0,
            "daily_cumulative_limit": 200.0,
            "trusted_recipients": ["0xPartnerContract"],
        },
    )

    client.post(
        "/autonomous-signing-airgap/evaluate",
        json={
            "tx_id": "api-tx-rej",
            "recipient": "0xPartnerContract",
            "amount": 80.0,
        },
    )

    # Reject
    rej_resp = client.post(
        "/autonomous-signing-airgap/step-up/reject",
        json={"tx_id": "api-tx-rej", "reason": "Operator denied"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["rejected"] is True

    # Try to approve non-existent or already rejected -> 404
    not_found = client.post(
        "/autonomous-signing-airgap/step-up/approve",
        json={"tx_id": "api-tx-rej"},
    )
    assert not_found.status_code == 404


def test_endpoint_kill_switch_lifecycle(client: TestClient) -> None:
    """Test emergency freeze trigger, check, block, and release."""
    # Trigger
    trig_resp = client.post(
        "/autonomous-signing-airgap/kill-switch/trigger",
        json={"reason": "Attacker payload detected in agent context"},
    )
    assert trig_resp.status_code == 200
    assert trig_resp.json()["is_kill_switch_active"] is True

    # Status
    status_resp = client.get("/autonomous-signing-airgap/kill-switch/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_kill_switch_active"] is True

    # Attempt evaluate during freeze
    frozen_eval = client.post(
        "/autonomous-signing-airgap/evaluate",
        json={
            "tx_id": "tx-freeze-test",
            "recipient": "0xSafeVendor",
            "amount": 5.0,
        },
    )
    assert frozen_eval.status_code == 200
    assert frozen_eval.json()["decision"] == "FROZEN_BY_KILL_SWITCH"
    assert frozen_eval.json()["is_approved_to_sign"] is False

    # Release
    rel_resp = client.post("/autonomous-signing-airgap/kill-switch/release")
    assert rel_resp.status_code == 200
    assert rel_resp.json()["is_kill_switch_active"] is False


def test_endpoint_quota_and_metrics(client: TestClient) -> None:
    """Test fetching active quota and operational metrics."""
    q_resp = client.get("/autonomous-signing-airgap/quota")
    assert q_resp.status_code == 200
    assert "single_tx_limit" in q_resp.json()

    m_resp = client.get("/autonomous-signing-airgap/metrics")
    assert m_resp.status_code == 200
    assert "evaluations_total" in m_resp.json()
