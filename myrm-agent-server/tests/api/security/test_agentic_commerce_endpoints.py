"""
[POS] tests/api/security/test_agentic_commerce_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.agentic_commerce_router, app.services.security.agentic_commerce_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Autonomous Agent Commerce Protocol & Zero-Knowledge Financial Vault.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.agentic_commerce_router import router as commerce_router
from app.services.security.agentic_commerce_service import (
    AgenticCommerceService,
    get_agentic_commerce_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = AgenticCommerceService()
    app = FastAPI()
    app.include_router(commerce_router)
    app.dependency_overrides[get_agentic_commerce_service] = lambda: test_service
    return TestClient(app)


def test_auto_approved_intent_and_settlement_endpoints(client: TestClient) -> None:
    """Validate POST /intents auto-approval and POST /settle execution."""
    # 1. Create intent ($4.00)
    intent_res = client.post(
        "/agentic-commerce/intents",
        json={
            "merchant": {
                "merchant_id": "m-aws-01",
                "merchant_name": "AWS Marketplace",
                "domain": "aws.amazon.com",
                "category": "cloud_compute",
                "is_whitelisted": True,
            },
            "amount_cents": 400,
            "currency": "USD",
            "line_items": ["Lambda test invocations"],
            "payment_rail": "STRIPE_AGENT_VIRTUAL_CARD",
        },
    )
    assert intent_res.status_code == 200
    idata = intent_res.json()
    assert idata["status"] == "AUTO_APPROVED"
    assert idata["token"] is not None
    token_str = idata["token"]["token_string"]
    intent_obj = idata["intent"]

    # 2. Settle transaction
    settle_res = client.post(
        "/agentic-commerce/settle",
        json={
            "token_string": token_str,
            "intent": intent_obj,
        },
    )
    assert settle_res.status_code == 200
    sdata = settle_res.json()
    assert sdata["status"] == "SETTLED"
    assert sdata["amount_cents"] == 400
    assert sdata["confirmation_code"].startswith("AUTH_")

    # 3. Verify budget status
    budget_res = client.get("/agentic-commerce/budget")
    assert budget_res.status_code == 200
    bdata = budget_res.json()
    assert bdata["daily_spent_cents"] == 400
    assert bdata["remaining_budget_cents"] == 5000 - 400

    # 4. Verify metrics
    metrics_res = client.get("/agentic-commerce/metrics")
    assert metrics_res.status_code == 200
    mdata = metrics_res.json()
    assert mdata["auto_approved_total"] == 1
    assert mdata["settlements_completed_total"] == 1


def test_hitl_approval_and_denial_endpoints(client: TestClient) -> None:
    """Validate HITL pending queue, confirmation, and denial flows."""
    # 1. Create intent requiring HITL ($15.00)
    intent_res = client.post(
        "/agentic-commerce/intents",
        json={
            "merchant": {
                "merchant_id": "m-gh-01",
                "merchant_name": "GitHub Copilot",
                "domain": "github.com",
                "category": "development_tools",
                "is_whitelisted": True,
            },
            "amount_cents": 1500,
            "currency": "USD",
        },
    )
    assert intent_res.status_code == 200
    idata = intent_res.json()
    assert idata["status"] == "PENDING_HITL_CONFIRMATION"
    assert idata["token"] is None
    intent_id = idata["intent"]["intent_id"]

    # 2. List pending HITL
    pending_res = client.get("/agentic-commerce/hitl/pending")
    assert pending_res.status_code == 200
    pending_list = pending_res.json()
    assert len(pending_list) == 1
    assert pending_list[0]["intent_id"] == intent_id

    # 3. Confirm HITL
    confirm_res = client.post(
        "/agentic-commerce/hitl/confirm",
        json={"intent_id": intent_id},
    )
    assert confirm_res.status_code == 200
    cdata = confirm_res.json()
    assert cdata["token"]["token_string"] != ""

    # 4. Create another intent to test denial ($10.00)
    res_deny = client.post(
        "/agentic-commerce/intents",
        json={
            "merchant": {
                "merchant_id": "m-gh-02",
                "merchant_name": "GitHub Copilot",
                "domain": "github.com",
                "category": "development_tools",
            },
            "amount_cents": 1000,
        },
    )
    deny_intent_id = res_deny.json()["intent"]["intent_id"]
    deny_res = client.post(
        "/agentic-commerce/hitl/deny",
        json={"intent_id": deny_intent_id},
    )
    assert deny_res.status_code == 200
    assert "denied and cancelled" in deny_res.json()["message"]


def test_budget_rejection_and_policy_update_endpoint(client: TestClient) -> None:
    """Validate budget limit exceeded response and dynamic PUT /budget policy update."""
    # 1. Excess amount intent ($25.00 > $20.00 ceiling)
    intent_res = client.post(
        "/agentic-commerce/intents",
        json={
            "merchant": {
                "merchant_id": "m-tool-01",
                "merchant_name": "Dev Tool",
                "domain": "devtool.io",
                "category": "development_tools",
            },
            "amount_cents": 2500,
        },
    )
    assert intent_res.status_code == 200
    assert intent_res.json()["status"] == "REJECTED_BUDGET_EXCEEDED"

    # 2. Update budget policy
    put_res = client.put(
        "/agentic-commerce/budget",
        json={
            "daily_hard_cap_cents": 20000,
            "single_transaction_max_cents": 10000,
            "auto_approval_threshold_cents": 1000,
            "allowed_categories": ["development_tools"],
        },
    )
    assert put_res.status_code == 200
    pdata = put_res.json()
    assert pdata["single_transaction_max_cents"] == 10000
