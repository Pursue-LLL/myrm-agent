"""
[POS] tests/unit/test_agentic_commerce_service.py
[INPUT] pytest, app.schemas.agentic_commerce, app.services.security.agentic_commerce_service
[OUTPUT] Unit tests for AgenticCommerceService

Validates service-level agentic commerce intents, spend guardrails, ZK vault, and settlements.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.agentic_commerce import (
    CommerceTransactionStatusResponse,
    ConfirmHITLRequest,
    CreatePaymentIntentRequest,
    DenyHITLRequest,
    MerchantSpecSchema,
    PaymentRailEnumResponse,
    SettleTransactionRequest,
    UpdateBudgetPolicyRequest,
)
from app.services.security.agentic_commerce_service import (
    AgenticCommerceService,
)


def _make_merchant(name: str = "Cloudflare Inc", cat: str = "cloud_compute") -> MerchantSpecSchema:
    return MerchantSpecSchema(
        merchant_id="m-cf-01",
        merchant_name=name,
        domain="cloudflare.com",
        category=cat,
        is_whitelisted=True,
    )


def test_service_auto_approved_intent_and_settlement() -> None:
    """Validate auto-approval for sub-$5 transactions and subsequent single-use token settlement."""
    service = AgenticCommerceService()

    # 1. Create intent ($3.50 = 350 cents)
    create_req = CreatePaymentIntentRequest(
        merchant=_make_merchant(),
        amount_cents=350,
        currency="USD",
        line_items=["KV Workers plan"],
        payment_rail=PaymentRailEnumResponse.STRIPE_AGENT_VIRTUAL_CARD,
    )
    res = service.create_payment_intent(create_req)
    assert res.status == CommerceTransactionStatusResponse.AUTO_APPROVED
    assert res.token is not None
    assert res.token.masked_card_last4 == "4242"
    assert res.token.is_consumed is False

    # 2. Settle transaction
    settle_req = SettleTransactionRequest(
        token_string=res.token.token_string,
        intent=res.intent,
    )
    receipt = service.settle_transaction(settle_req)
    assert receipt.status == CommerceTransactionStatusResponse.SETTLED
    assert receipt.amount_cents == 350
    assert receipt.confirmation_code.startswith("AUTH_")

    # 3. Check budget and metrics
    budget = service.get_budget_status()
    assert budget.daily_spent_cents == 350
    assert budget.remaining_budget_cents == 5000 - 350

    metrics = service.get_metrics()
    assert metrics.auto_approved_total == 1
    assert metrics.settlements_completed_total == 1
    assert metrics.total_spent_cents == 350


def test_service_hitl_intent_approval_lifecycle() -> None:
    """Validate HITL confirmation workflow for transactions between auto-approve limit and hard ceiling."""
    service = AgenticCommerceService()

    # 1. Intent for $12.00 (1200 cents)
    create_req = CreatePaymentIntentRequest(
        merchant=_make_merchant(name="OpenAI API", cat="api_credits"),
        amount_cents=1200,
        currency="USD",
        line_items=["Tier 1 API credits"],
        payment_rail=PaymentRailEnumResponse.VISA_VIRTUAL_ACCOUNT,
    )
    res = service.create_payment_intent(create_req)
    assert res.status == CommerceTransactionStatusResponse.PENDING_HITL_CONFIRMATION
    assert res.token is None

    # 2. Pending list
    pending = service.list_pending_hitl_intents()
    assert len(pending) == 1
    assert pending[0].intent_id == res.intent.intent_id

    # 3. Confirm HITL
    confirm_res = service.confirm_hitl(ConfirmHITLRequest(intent_id=res.intent.intent_id))
    assert confirm_res.intent.intent_id == res.intent.intent_id
    assert confirm_res.token.token_string != ""
    assert len(service.list_pending_hitl_intents()) == 0

    # 4. Settle HITL intent
    settle_req = SettleTransactionRequest(
        token_string=confirm_res.token.token_string,
        intent=confirm_res.intent,
    )
    receipt = service.settle_transaction(settle_req)
    assert receipt.status == CommerceTransactionStatusResponse.SETTLED
    assert receipt.amount_cents == 1200


def test_service_hitl_denial() -> None:
    """Validate user operator denial of pending payment tickets."""
    service = AgenticCommerceService()

    res = service.create_payment_intent(
        CreatePaymentIntentRequest(
            merchant=_make_merchant(),
            amount_cents=1500,
            currency="USD",
        )
    )
    assert res.status == CommerceTransactionStatusResponse.PENDING_HITL_CONFIRMATION

    deny_res = service.deny_hitl(DenyHITLRequest(intent_id=res.intent.intent_id))
    assert deny_res.intent.intent_id == res.intent.intent_id
    assert "denied and cancelled" in deny_res.message
    assert len(service.list_pending_hitl_intents()) == 0

    metrics = service.get_metrics()
    assert metrics.hitl_denied_total == 1


def test_service_budget_rejection_and_policy_update() -> None:
    """Validate instant rejection of over-budget intents and dynamic policy reconfiguration."""
    service = AgenticCommerceService()

    # 1. Single transaction max exceeded ($25.00 > $20.00)
    res = service.create_payment_intent(
        CreatePaymentIntentRequest(
            merchant=_make_merchant(),
            amount_cents=2500,
            currency="USD",
        )
    )
    assert res.status == CommerceTransactionStatusResponse.REJECTED_BUDGET_EXCEEDED
    assert "exceeds single-purchase hard ceiling" in res.explanation

    # 2. Update policy to allow $30.00
    updated_budget = service.update_budget_policy(
        UpdateBudgetPolicyRequest(
            daily_hard_cap_cents=10000,
            single_transaction_max_cents=5000,
            auto_approval_threshold_cents=1000,
            allowed_categories=["cloud_compute"],
        )
    )
    assert updated_budget.single_transaction_max_cents == 5000
    assert updated_budget.daily_hard_cap_cents == 10000

    # 3. Now 2500 cents is eligible for HITL under 5000 limit
    res2 = service.create_payment_intent(
        CreatePaymentIntentRequest(
            merchant=_make_merchant(),
            amount_cents=2500,
            currency="USD",
        )
    )
    assert res2.status == CommerceTransactionStatusResponse.PENDING_HITL_CONFIRMATION
