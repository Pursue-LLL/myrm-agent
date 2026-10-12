"""
[POS] app/services/security/agentic_commerce_service.py
[INPUT] myrm_agent_harness.core.security.agentic_commerce, app.schemas.agentic_commerce
[OUTPUT] AgenticCommerceService, get_agentic_commerce_service

Domain service mediating requests for Autonomous Agent Commerce Protocol & Zero-Knowledge Financial Vault.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.agentic_commerce import (
    AgenticCommerceSuite,
    EphemeralPaymentToken,
    FinancialBudgetPolicy,
    MerchantSpec,
    PaymentIntent,
    PaymentRailEnum,
    SettlementReceipt,
)

from app.schemas.agentic_commerce import (
    BudgetStatusResponse,
    CommerceMetricsResponse,
    CommerceTransactionStatusResponse,
    ConfirmHITLRequest,
    ConfirmHITLResponse,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    DenyHITLRequest,
    DenyHITLResponse,
    EphemeralPaymentTokenSchema,
    MerchantSpecSchema,
    PaymentIntentSchema,
    PaymentRailEnumResponse,
    SettlementReceiptSchema,
    SettleTransactionRequest,
    UpdateBudgetPolicyRequest,
)


class AgenticCommerceService:
    """Service orchestrating agentic commerce intents, spend guardrails, and ZK payment vault."""

    def __init__(self, suite: AgenticCommerceSuite | None = None) -> None:
        self._suite = suite or AgenticCommerceSuite()

    def create_payment_intent(self, req: CreatePaymentIntentRequest) -> CreatePaymentIntentResponse:
        """Create structured payment intent and evaluate against spend guardrail."""
        merchant = MerchantSpec(
            merchant_id=req.merchant.merchant_id,
            merchant_name=req.merchant.merchant_name,
            domain=req.merchant.domain,
            category=req.merchant.category,
            is_whitelisted=req.merchant.is_whitelisted,
        )
        rail = PaymentRailEnum(req.payment_rail.value)
        intent, status, explanation, token = self._suite.create_payment_intent(
            merchant=merchant,
            amount_cents=req.amount_cents,
            currency=req.currency,
            line_items=tuple(req.line_items),
            payment_rail=rail,
        )

        intent_schema = self._to_intent_schema(intent)
        token_schema = self._to_token_schema(token) if token else None

        return CreatePaymentIntentResponse(
            intent=intent_schema,
            status=CommerceTransactionStatusResponse(status.value),
            explanation=explanation,
            token=token_schema,
        )

    def confirm_hitl(self, req: ConfirmHITLRequest) -> ConfirmHITLResponse:
        """Confirm a pending human-in-the-loop transaction and mint single-use token."""
        intent, token = self._suite.confirm_hitl_and_mint(req.intent_id)
        return ConfirmHITLResponse(
            intent=self._to_intent_schema(intent),
            token=self._to_token_schema(token),
        )

    def deny_hitl(self, req: DenyHITLRequest) -> DenyHITLResponse:
        """Explicitly deny a pending human-in-the-loop payment ticket."""
        intent = self._suite.deny_hitl(req.intent_id)
        return DenyHITLResponse(
            intent=self._to_intent_schema(intent),
            message=f"Transaction ticket {intent.intent_id} has been denied and cancelled.",
        )

    def settle_transaction(self, req: SettleTransactionRequest) -> SettlementReceiptSchema:
        """Execute settlement using minted token and return immutable receipt."""
        intent = PaymentIntent(
            intent_id=req.intent.intent_id,
            merchant=MerchantSpec(
                merchant_id=req.intent.merchant.merchant_id,
                merchant_name=req.intent.merchant.merchant_name,
                domain=req.intent.merchant.domain,
                category=req.intent.merchant.category,
                is_whitelisted=req.intent.merchant.is_whitelisted,
            ),
            amount_cents=req.intent.amount_cents,
            currency=req.intent.currency,
            line_items=tuple(req.intent.line_items),
            payment_rail=PaymentRailEnum(req.intent.payment_rail.value),
            created_at=req.intent.created_at,
        )

        receipt = self._suite.settle_transaction(
            token_string=req.token_string,
            intent=intent,
        )
        return self._to_receipt_schema(receipt)

    def get_budget_status(self) -> BudgetStatusResponse:
        """Retrieve active spend limits and remaining allowance."""
        status = self._suite.get_budget_status()
        return BudgetStatusResponse(
            daily_hard_cap_cents=status["daily_hard_cap_cents"],
            daily_spent_cents=status["daily_spent_cents"],
            remaining_budget_cents=status["remaining_budget_cents"],
            single_transaction_max_cents=status["single_transaction_max_cents"],
            auto_approval_threshold_cents=status["auto_approval_threshold_cents"],
        )

    def update_budget_policy(self, req: UpdateBudgetPolicyRequest) -> BudgetStatusResponse:
        """Update multi-tier financial budget guardrail thresholds."""
        new_policy = FinancialBudgetPolicy(
            daily_hard_cap_cents=req.daily_hard_cap_cents,
            single_transaction_max_cents=req.single_transaction_max_cents,
            auto_approval_threshold_cents=req.auto_approval_threshold_cents,
            allowed_categories=tuple(req.allowed_categories),
        )
        self._suite.update_budget_policy(new_policy)
        return self.get_budget_status()

    def list_pending_hitl_intents(self) -> list[PaymentIntentSchema]:
        """List all pending transaction intents awaiting human decision."""
        intents = self._suite.list_pending_hitl_intents()
        return [self._to_intent_schema(i) for i in intents]

    def get_metrics(self) -> CommerceMetricsResponse:
        """Fetch cumulative commerce metrics."""
        m = self._suite.metrics
        return CommerceMetricsResponse(
            intents_created_total=m.intents_created_total,
            auto_approved_total=m.auto_approved_total,
            hitl_approvals_requested_total=m.hitl_approvals_requested_total,
            hitl_approved_total=m.hitl_approved_total,
            hitl_denied_total=m.hitl_denied_total,
            budget_rejections_total=m.budget_rejections_total,
            settlements_completed_total=m.settlements_completed_total,
            tokens_minted_total=m.tokens_minted_total,
            total_spent_cents=m.total_spent_cents,
        )

    @staticmethod
    def _to_intent_schema(intent: PaymentIntent) -> PaymentIntentSchema:
        return PaymentIntentSchema(
            intent_id=intent.intent_id,
            merchant=MerchantSpecSchema(
                merchant_id=intent.merchant.merchant_id,
                merchant_name=intent.merchant.merchant_name,
                domain=intent.merchant.domain,
                category=intent.merchant.category,
                is_whitelisted=intent.merchant.is_whitelisted,
            ),
            amount_cents=intent.amount_cents,
            currency=intent.currency,
            line_items=list(intent.line_items),
            payment_rail=PaymentRailEnumResponse(intent.payment_rail.value),
            created_at=intent.created_at,
        )

    @staticmethod
    def _to_token_schema(token: EphemeralPaymentToken) -> EphemeralPaymentTokenSchema:
        return EphemeralPaymentTokenSchema(
            token_id=token.token_id,
            intent_id=token.intent_id,
            masked_card_last4=token.masked_card_last4,
            token_string=token.token_string,
            max_amount_cents=token.max_amount_cents,
            expires_at=token.expires_at,
            is_consumed=token.is_consumed,
        )

    @staticmethod
    def _to_receipt_schema(receipt: SettlementReceipt) -> SettlementReceiptSchema:
        return SettlementReceiptSchema(
            receipt_id=receipt.receipt_id,
            intent_id=receipt.intent_id,
            status=CommerceTransactionStatusResponse(receipt.status.value),
            amount_cents=receipt.amount_cents,
            currency=receipt.currency,
            merchant_name=receipt.merchant_name,
            payment_rail=PaymentRailEnumResponse(receipt.payment_rail.value),
            confirmation_code=receipt.confirmation_code,
            settled_at=receipt.settled_at,
        )


_default_service: AgenticCommerceService | None = None


def get_agentic_commerce_service() -> AgenticCommerceService:
    """Dependency injection provider for AgenticCommerceService."""
    global _default_service
    if _default_service is None:
        _default_service = AgenticCommerceService()
    return _default_service
