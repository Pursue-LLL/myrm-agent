"""
[POS] tests/api/security/test_consumer_action_guard_endpoints.py
[INPUT] app.api.security.consumer_action_guard_router, app.services.security.consumer_action_guard_service
[OUTPUT] endpoint tests

API endpoint tests for Consumer-Grade Real-World Action Explosion and Velocity Limiter Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.consumer_action_guard_router import (
    router as consumer_action_guard_router,
)
from app.services.security.consumer_action_guard_service import (
    ConsumerActionGuardService,
    get_consumer_action_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ConsumerActionGuardService()
    app = FastAPI()
    app.include_router(consumer_action_guard_router)
    app.dependency_overrides[get_consumer_action_guard_service] = lambda: test_service
    return TestClient(app)


def test_evaluate_order_autonomous(client: TestClient) -> None:
    """Test POST /consumer-guard/evaluate-order for safe autonomous order."""
    payload = {
        "order_id": "ord-api-001",
        "agent_id": "agent-api-001",
        "action_type": "FOOD_DELIVERY",
        "item_name": "Salad Bowl",
        "quantity": 1,
        "unit_price": 14.5,
        "total_amount": 14.5,
        "recipient_name": "Charlie",
        "recipient_phone": "+1-555-8888",
        "delivery_address": "88 Tech Boulevard",
        "merchant_id": "green-leaf",
        "metadata": {"urgent": "false"},
    }
    resp = client.post("/consumer-guard/evaluate-order", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_allowed"] is True
    assert data["verdict"] == "ALLOW_AUTONOMOUS"
    assert data["requires_hitl"] is False
    assert data["confirmation_card_summary"] is None


def test_evaluate_order_requires_hitl(client: TestClient) -> None:
    """Test POST /consumer-guard/evaluate-order triggering grandma burrito HITL card."""
    payload = {
        "order_id": "ord-api-burrito",
        "agent_id": "agent-api-burrito",
        "action_type": "FOOD_DELIVERY",
        "item_name": "Cheese Burrito",
        "quantity": 25,
        "unit_price": 6.0,
        "total_amount": 150.0,
        "recipient_name": "Grandma",
        "recipient_phone": "+1-555-9999",
        "delivery_address": "404 Elm St",
        "merchant_id": "taco-world",
        "metadata": {},
    }
    resp = client.post("/consumer-guard/evaluate-order", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_allowed"] is False
    assert data["verdict"] == "REQUIRES_HUMAN_CONFIRMATION"
    assert data["requires_hitl"] is True
    assert data["confirmation_card_summary"] is not None
    assert "Action Confirmation Required" in data["confirmation_card_summary"]
    assert "Cheese Burrito x 25" in data["confirmation_card_summary"]


def test_confirm_order_endpoint(client: TestClient) -> None:
    """Test POST /consumer-guard/confirm-order and spend tallying."""
    payload = {
        "order_id": "ord-api-confirm-1",
        "agent_id": "agent-api-confirm",
        "action_type": "FOOD_DELIVERY",
        "total_amount": 42.5,
    }
    resp = client.post("/consumer-guard/confirm-order", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == "ord-api-confirm-1"
    assert data["agent_id"] == "agent-api-confirm"
    assert data["is_confirmed"] is True
    assert data["current_daily_spent"] == 42.5


def test_agent_policy_lifecycle_endpoints(client: TestClient) -> None:
    """Test GET and PUT /consumer-guard/agents/{agent_id}/policy."""
    agent_id = "agent-policy-cfg-01"

    # Default policy
    get_resp = client.get(f"/consumer-guard/agents/{agent_id}/policy")
    assert get_resp.status_code == 200
    default_policy = get_resp.json()
    assert default_policy["max_item_quantity"] == 5
    assert default_policy["daily_spend_ceiling"] == 200.0

    # Update policy
    put_payload = {
        "max_item_quantity": 2,
        "max_single_action_amount": 40.0,
        "velocity_window_seconds": 1800.0,
        "max_actions_per_window": 1,
        "daily_spend_ceiling": 80.0,
        "allowlisted_addresses": ["Safe Haven Apt 3B"],
        "allowlisted_phones": ["+1-555-0011"],
        "allowlisted_merchants": ["fresh-mart"],
    }
    put_resp = client.put(f"/consumer-guard/agents/{agent_id}/policy", json=put_payload)
    assert put_resp.status_code == 200
    updated_data = put_resp.json()
    assert updated_data["max_item_quantity"] == 2
    assert updated_data["allowlisted_addresses"] == ["Safe Haven Apt 3B"]

    # Verify updated GET
    get_resp2 = client.get(f"/consumer-guard/agents/{agent_id}/policy")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["max_item_quantity"] == 2


def test_metrics_endpoint(client: TestClient) -> None:
    """Test GET /consumer-guard/metrics."""
    # Trigger an autonomous evaluation
    client.post(
        "/consumer-guard/evaluate-order",
        json={
            "order_id": "ord-metrics-1",
            "agent_id": "agent-metrics",
            "action_type": "GROCERY_PURCHASE",
            "item_name": "Organic Milk",
            "quantity": 1,
            "unit_price": 5.0,
            "total_amount": 5.0,
            "recipient_name": "Dave",
            "recipient_phone": "+1-555-4321",
            "delivery_address": "55 Lake View",
            "merchant_id": "dairy-farm",
            "metadata": {},
        },
    )

    resp = client.get("/consumer-guard/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_evaluations"] >= 1
    assert data["autonomous_approvals"] >= 1
