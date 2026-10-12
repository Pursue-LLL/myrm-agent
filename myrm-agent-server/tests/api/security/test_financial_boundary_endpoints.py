"""Integration tests for Financial Boundary and Wallet Air-Gap Guard API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.financial_boundary_router import router as financial_boundary_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting financial_boundary_router."""
    test_app = FastAPI(title="Financial Boundary Test App")
    test_app.include_router(financial_boundary_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_intent_micro_and_card_lifecycle(client: TestClient) -> None:
    # 1. Micro-transaction within bounds
    micro_resp = client.post(
        "/api/v1/security/financial-boundary/evaluate-intent",
        json={
            "intent_id": "intent_api_01",
            "task_id": "task_api_tx",
            "action_type": "transfer",
            "asset_symbol": "USDC",
            "amount": 2.0,
            "estimated_usd_value": 2.0,
            "recipient_address": "0x1111111111111111111111111111111111111111",
            "justification": "Autonomous micro payment",
        },
    )
    assert micro_resp.status_code == 200
    assert micro_resp.json()["permitted_autonomous_execution"] is True
    assert micro_resp.json()["requires_human_confirmation"] is False

    # 2. Large transaction triggering confirmation card
    large_resp = client.post(
        "/api/v1/security/financial-boundary/evaluate-intent",
        json={
            "intent_id": "intent_api_02",
            "task_id": "task_api_tx",
            "action_type": "swap",
            "asset_symbol": "ETH",
            "amount": 0.02,
            "estimated_usd_value": 30.0,
            "recipient_address": "0x2222222222222222222222222222222222222222",
            "justification": "Rebalancing reserve pool",
        },
    )
    assert large_resp.status_code == 200
    large_data = large_resp.json()
    assert large_data["permitted_autonomous_execution"] is False
    assert large_data["requires_human_confirmation"] is True
    card_id = large_data["confirmation_card_id"]
    assert card_id != ""

    # 3. List cards
    cards_resp = client.get("/api/v1/security/financial-boundary/confirmation-cards")
    assert cards_resp.status_code == 200
    cards = cards_resp.json()
    assert any(c["card_id"] == card_id for c in cards)

    # 4. Approve card
    approve_resp = client.post(
        f"/api/v1/security/financial-boundary/confirmation-cards/{card_id}/approve"
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


def test_air_gap_leak_blocked_via_api(client: TestClient) -> None:
    leak_resp = client.post(
        "/api/v1/security/financial-boundary/evaluate-intent",
        json={
            "intent_id": "intent_leak_01",
            "task_id": "task_leak",
            "action_type": "transfer",
            "asset_symbol": "ETH",
            "amount": 1.0,
            "estimated_usd_value": 1.0,
            "recipient_address": "0x4444444444444444444444444444444444444444",
            "justification": "Using 0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f36088a",
        },
    )
    assert leak_resp.status_code == 400
    assert "air-gap violation" in leak_resp.json()["detail"].lower()


def test_policy_and_stats_endpoints(client: TestClient) -> None:
    # 1. Get policy
    get_pol = client.get("/api/v1/security/financial-boundary/policy")
    assert get_pol.status_code == 200
    assert "daily_ceiling_usd" in get_pol.json()

    # 2. Update policy
    up_pol = client.post(
        "/api/v1/security/financial-boundary/policy",
        json={
            "daily_ceiling_usd": 150.0,
            "single_transaction_ceiling_usd": 10.0,
            "require_two_person_confirmation_above_usd": 10.0,
            "allowed_asset_symbols": ["USDC", "ETH", "SOL"],
        },
    )
    assert up_pol.status_code == 200
    assert up_pol.json()["daily_ceiling_usd"] == 150.0

    # 3. Get stats
    stats_resp = client.get("/api/v1/security/financial-boundary/stats")
    assert stats_resp.status_code == 200
    s_data = stats_resp.json()
    assert s_data["daily_ceiling_usd"] == 150.0
    assert "current_spend_usd" in s_data
