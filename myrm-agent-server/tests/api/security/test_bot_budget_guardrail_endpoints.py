"""API endpoint tests for Autonomous Bot Budget Guardrail and Token Ceiling Circuit Breaker."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.bot_budget_guardrail_router import (
    router as bot_budget_guardrail_router,
)
from app.services.security.bot_budget_guardrail_service import (
    BotBudgetGuardrailService,
    get_bot_budget_guardrail_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = BotBudgetGuardrailService()
    test_service.reset_all()
    app = FastAPI()
    app.include_router(bot_budget_guardrail_router)
    app.dependency_overrides[get_bot_budget_guardrail_service] = lambda: test_service
    return TestClient(app)


def test_register_and_get_bot_quota_endpoint(client: TestClient) -> None:
    # 1. Register a new bot quota
    reg_resp = client.post(
        "/security/bot-budget-guardrail/register",
        json={
            "bot_id": "test-bot-telegram",
            "bot_name": "Test Telegram Channel Bot",
            "sandbox_mode": "ISOLATED_SANDBOX",
            "token_ceiling": 500_000,
            "cost_ceiling_usd": 5.0,
            "warning_threshold": 0.8,
        },
    )
    assert reg_resp.status_code == 200
    data = reg_resp.json()
    assert data["bot_id"] == "test-bot-telegram"
    assert data["token_ceiling"] == 500_000
    assert data["cost_ceiling_usd"] == 5.0
    assert data["state"] == "CLOSED"

    # 2. Get status
    status_resp = client.get("/security/bot-budget-guardrail/status/test-bot-telegram")
    assert status_resp.status_code == 200
    st_data = status_resp.json()
    assert st_data["bot_id"] == "test-bot-telegram"
    assert st_data["used_tokens"] == 0

    # 3. Query non-existent bot status -> 404
    missing_resp = client.get("/security/bot-budget-guardrail/status/unknown-bot")
    assert missing_resp.status_code == 404


def test_consume_budget_tiered_endpoints(client: TestClient) -> None:
    # Register quota
    client.post(
        "/security/bot-budget-guardrail/register",
        json={
            "bot_id": "test-bot-cron",
            "bot_name": "Scheduled Cron Bot",
            "sandbox_mode": "CORE_PROTECTED",
            "token_ceiling": 100_000,
            "cost_ceiling_usd": 1.0,
            "warning_threshold": 0.8,
        },
    )

    # Normal consume (20%)
    c1_resp = client.post(
        "/security/bot-budget-guardrail/consume",
        json={"bot_id": "test-bot-cron", "tokens": 20_000, "cost_usd": 0.2},
    )
    assert c1_resp.status_code == 200
    c1 = c1_resp.json()
    assert c1["allowed"] is True
    assert c1["state"] == "CLOSED"

    # Soft warning consume (65% more, total 85%)
    c2_resp = client.post(
        "/security/bot-budget-guardrail/consume",
        json={"bot_id": "test-bot-cron", "tokens": 65_000, "cost_usd": 0.65},
    )
    assert c2_resp.status_code == 200
    c2 = c2_resp.json()
    assert c2["allowed"] is True
    assert c2["state"] == "HALF_OPEN"

    # Hard ceiling breach (attempt 20% more, total would be 105% > 100%)
    c3_resp = client.post(
        "/security/bot-budget-guardrail/consume",
        json={"bot_id": "test-bot-cron", "tokens": 20_000, "cost_usd": 0.2},
    )
    assert c3_resp.status_code == 200
    c3 = c3_resp.json()
    assert c3["allowed"] is False
    assert c3["state"] == "OPEN_FROZEN"
    assert "Hard ceiling circuit breaker tripped" in c3["rejection_reason"]


def test_refuel_and_list_endpoints(client: TestClient) -> None:
    client.post(
        "/security/bot-budget-guardrail/register",
        json={
            "bot_id": "test-bot-wechat",
            "bot_name": "WeChat Assistant",
            "sandbox_mode": "ISOLATED_SANDBOX",
            "token_ceiling": 10_000,
            "cost_ceiling_usd": 0.1,
            "warning_threshold": 0.8,
        },
    )

    # Trip breaker
    client.post(
        "/security/bot-budget-guardrail/consume",
        json={"bot_id": "test-bot-wechat", "tokens": 15_000, "cost_usd": 0.15},
    )

    # Refuel
    refuel_resp = client.post(
        "/security/bot-budget-guardrail/refuel",
        json={
            "bot_id": "test-bot-wechat",
            "additional_tokens": 50_000,
            "additional_cost_usd": 0.5,
            "reset_state": True,
        },
    )
    assert refuel_resp.status_code == 200
    ref_data = refuel_resp.json()
    assert ref_data["token_ceiling"] == 60_000
    assert ref_data["cost_ceiling_usd"] == 0.6
    assert ref_data["state"] == "CLOSED"

    # List quotas
    list_resp = client.get("/security/bot-budget-guardrail/list")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["quotas"][0]["bot_id"] == "test-bot-wechat"

    # Refuel non-existent bot -> 404
    missing_refuel = client.post(
        "/security/bot-budget-guardrail/refuel",
        json={"bot_id": "non-existent-bot", "additional_tokens": 1000},
    )
    assert missing_refuel.status_code == 404
