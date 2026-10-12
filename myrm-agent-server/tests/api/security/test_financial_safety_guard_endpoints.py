"""API endpoint tests for Autonomous Financial Execution Safety Guard."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.financial_safety_guard import (
    FinancialBudgetConfig,
    FinancialSafetyGuard,
)

from app.api.security.financial_safety_guard_router import (
    router as financial_safety_guard_router,
)
from app.services.security.financial_safety_guard_service import (
    FinancialSafetyGuardService,
    get_financial_safety_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    cfg = FinancialBudgetConfig(
        single_tx_limit_usd=50.0,
        daily_limit_usd=200.0,
        max_allowed_slippage_bps=100,  # 1.0%
        critical_risk_score_threshold=80,
    )
    test_service = FinancialSafetyGuardService(guard=FinancialSafetyGuard(config=cfg))
    app = FastAPI()
    app.include_router(financial_safety_guard_router)
    app.dependency_overrides[get_financial_safety_guard_service] = lambda: test_service
    return TestClient(app)


def test_evaluate_endpoint_approved(client: TestClient) -> None:
    resp = client.post(
        "/security/financial-safety/evaluate",
        json={
            "tx_id": "tx_api_01",
            "source_account": "0xuser1",
            "target_contract_or_recipient": "0xdex",
            "asset_symbol": "USDC",
            "amount": 20.0,
            "amount_usd": 20.0,
            "slippage_tolerance_bps": 50,
            "max_fee_limit": 2.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "APPROVE"
    assert data["requires_manual_approval"] is False
    assert data["daily_spent_usd"] == 20.0
    assert data["remaining_daily_budget_usd"] == 180.0


def test_evaluate_and_approve_suspended_transaction(client: TestClient) -> None:
    # 1. Evaluate tx exceeding single limit 50 USD
    resp_eval = client.post(
        "/security/financial-safety/evaluate",
        json={
            "tx_id": "tx_api_02",
            "source_account": "0xuser1",
            "target_contract_or_recipient": "0xvault",
            "asset_symbol": "USDT",
            "amount": 90.0,
            "amount_usd": 90.0,
        },
    )
    assert resp_eval.status_code == 200
    eval_data = resp_eval.json()
    assert eval_data["decision"] == "ASK_CONFIRMATION"
    assert eval_data["requires_manual_approval"] is True

    # 2. Approve manually
    resp_app = client.post(
        "/security/financial-safety/approve",
        json={"tx_id": "tx_api_02"},
    )
    assert resp_app.status_code == 200
    app_data = resp_app.json()
    assert app_data["decision"] == "APPROVE"
    assert app_data["daily_spent_usd"] == 90.0

    # 3. Approve non-existent returns 404
    resp_404 = client.post(
        "/security/financial-safety/approve",
        json={"tx_id": "tx_does_not_exist"},
    )
    assert resp_404.status_code == 404


def test_evaluate_slippage_breaker_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/security/financial-safety/evaluate",
        json={
            "tx_id": "tx_api_03",
            "source_account": "0xuser1",
            "target_contract_or_recipient": "0xamm",
            "asset_symbol": "ETH",
            "amount": 1000.0,
            "amount_usd": 3000.0,  # massive market impact
            "slippage_tolerance_bps": 200,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "REJECT_BREAKER"
    assert "circuit breaker triggered" in data["rejection_reason"]


def test_budget_and_history_endpoints(client: TestClient) -> None:
    # 1. Get budget
    resp_bg = client.get("/security/financial-safety/budget")
    assert resp_bg.status_code == 200
    assert resp_bg.json()["daily_limit_usd"] == 200.0

    # 2. Update budget
    resp_up = client.put(
        "/security/financial-safety/budget",
        json={"daily_limit_usd": 1000.0, "single_tx_limit_usd": 200.0},
    )
    assert resp_up.status_code == 200
    assert resp_up.json()["daily_limit_usd"] == 1000.0
    assert resp_up.json()["single_tx_limit_usd"] == 200.0

    # 3. Reset budget
    resp_rs = client.post("/security/financial-safety/budget/reset")
    assert resp_rs.status_code == 200
    assert resp_rs.json()["daily_spent_usd"] == 0.0

    # 4. History
    resp_hist = client.get("/security/financial-safety/history?limit=10")
    assert resp_hist.status_code == 200
    assert isinstance(resp_hist.json(), list)
