"""Unit test suite for BotBudgetGuardrailService."""

from __future__ import annotations

import pytest

from app.schemas.bot_budget_guardrail import (
    ConsumeBudgetRequest,
    RefuelBotQuotaRequest,
    RegisterBotQuotaRequest,
)
from app.services.security.bot_budget_guardrail_service import (
    BotBudgetGuardrailService,
)


@pytest.fixture
def service() -> BotBudgetGuardrailService:
    svc = BotBudgetGuardrailService()
    svc.reset_all()
    return svc


def test_register_and_get_quota_status(service: BotBudgetGuardrailService) -> None:
    req = RegisterBotQuotaRequest(
        bot_id="tg-bot-01",
        bot_name="Telegram News Bot",
        sandbox_mode="ISOLATED_SANDBOX",
        token_ceiling=200_000,
        cost_ceiling_usd=2.0,
        warning_threshold=0.8,
    )
    res = service.register_quota(req)
    assert res.bot_id == "tg-bot-01"
    assert res.token_ceiling == 200_000
    assert pytest.approx(res.cost_ceiling_usd) == 2.0
    assert res.state == "CLOSED"
    assert res.used_tokens == 0
    assert pytest.approx(res.used_cost_usd) == 0.0

    queried = service.get_quota_status("tg-bot-01")
    assert queried is not None
    assert queried.bot_id == "tg-bot-01"


def test_consume_budget_tiered_breaker(service: BotBudgetGuardrailService) -> None:
    reg_req = RegisterBotQuotaRequest(
        bot_id="feishu-digest-01",
        bot_name="Feishu Digest Bot",
        sandbox_mode="CORE_PROTECTED",
        token_ceiling=100_000,
        cost_ceiling_usd=1.0,
        warning_threshold=0.8,
    )
    service.register_quota(reg_req)

    # 1. Normal consumption (30%)
    c1 = service.consume_budget(
        ConsumeBudgetRequest(bot_id="feishu-digest-01", tokens=30_000, cost_usd=0.3)
    )
    assert c1.allowed is True
    assert c1.state == "CLOSED"
    assert c1.tokens_remaining == 70_000

    # 2. Warning consumption (total 85%)
    c2 = service.consume_budget(
        ConsumeBudgetRequest(bot_id="feishu-digest-01", tokens=55_000, cost_usd=0.55)
    )
    assert c2.allowed is True
    assert c2.state == "HALF_OPEN"
    assert c2.tokens_remaining == 15_000

    # 3. Hard ceiling breach (total would be 105% > 100%)
    c3 = service.consume_budget(
        ConsumeBudgetRequest(bot_id="feishu-digest-01", tokens=20_000, cost_usd=0.2)
    )
    assert c3.allowed is False
    assert c3.state == "OPEN_FROZEN"
    assert "Hard ceiling circuit breaker tripped" in (c3.rejection_reason or "")


def test_refuel_quota_and_reset(service: BotBudgetGuardrailService) -> None:
    reg_req = RegisterBotQuotaRequest(
        bot_id="wechat-helper",
        bot_name="WeChat Auto Helper",
        sandbox_mode="ISOLATED_SANDBOX",
        token_ceiling=10_000,
        cost_ceiling_usd=0.1,
        warning_threshold=0.8,
    )
    service.register_quota(reg_req)

    # Trip breaker
    service.consume_budget(
        ConsumeBudgetRequest(bot_id="wechat-helper", tokens=12_000, cost_usd=0.12)
    )
    st = service.get_quota_status("wechat-helper")
    assert st is not None
    assert st.state == "OPEN_FROZEN"

    # Refuel
    refuel_req = RefuelBotQuotaRequest(
        bot_id="wechat-helper",
        additional_tokens=50_000,
        additional_cost_usd=0.5,
        reset_state=True,
    )
    refueled = service.refuel_quota(refuel_req)
    assert refueled.token_ceiling == 60_000
    assert pytest.approx(refueled.cost_ceiling_usd) == 0.6
    assert refueled.state == "CLOSED"
    assert refueled.frozen_at is None


def test_list_quotas(service: BotBudgetGuardrailService) -> None:
    service.register_quota(
        RegisterBotQuotaRequest(
            bot_id="bot-a",
            bot_name="Bot A",
            sandbox_mode="ISOLATED_SANDBOX",
            token_ceiling=10_000,
            cost_ceiling_usd=0.1,
        )
    )
    service.register_quota(
        RegisterBotQuotaRequest(
            bot_id="bot-b",
            bot_name="Bot B",
            sandbox_mode="CORE_PROTECTED",
            token_ceiling=20_000,
            cost_ceiling_usd=0.2,
        )
    )
    all_quotas = service.list_quotas()
    assert all_quotas.total == 2
    bot_ids = {q.bot_id for q in all_quotas.quotas}
    assert bot_ids == {"bot-a", "bot-b"}
