"""
[POS] app/schemas/agentic_commerce.py
[INPUT] pydantic, enum
[OUTPUT] PaymentRailEnumResponse, CommerceTransactionStatusResponse, MerchantSpecSchema, PaymentIntentSchema, EphemeralPaymentTokenSchema, FinancialBudgetPolicySchema, SettlementReceiptSchema, CreatePaymentIntentRequest, CreatePaymentIntentResponse, ConfirmHITLRequest, ConfirmHITLResponse, DenyHITLRequest, DenyHITLResponse, SettleTransactionRequest, BudgetStatusResponse, UpdateBudgetPolicyRequest, CommerceMetricsResponse

Pydantic schemas for Autonomous Agent Commerce Protocol & Zero-Knowledge Financial Vault Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PaymentRailEnumResponse(StrEnum):
    """Payment settlement rails supported by the agentic commerce protocol."""

    STRIPE_AGENT_VIRTUAL_CARD = "STRIPE_AGENT_VIRTUAL_CARD"
    PAYPAL_COMMERCE = "PAYPAL_COMMERCE"
    VISA_VIRTUAL_ACCOUNT = "VISA_VIRTUAL_ACCOUNT"
    MOCK_SANDBOX = "MOCK_SANDBOX"


class CommerceTransactionStatusResponse(StrEnum):
    """Lifecycle status of an agentic purchase or subscription transaction."""

    DRAFT_INTENT = "DRAFT_INTENT"
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_HITL_CONFIRMATION = "PENDING_HITL_CONFIRMATION"
    SETTLED = "SETTLED"
    REJECTED_BUDGET_EXCEEDED = "REJECTED_BUDGET_EXCEEDED"
    REJECTED_USER_DENIED = "REJECTED_USER_DENIED"


class MerchantSpecSchema(BaseModel):
    """Descriptor of a merchant or digital vendor evaluated for commerce."""

    merchant_id: str = Field(..., min_length=1, description="Merchant unique ID")
    merchant_name: str = Field(..., min_length=1, description="Display name of merchant")
    domain: str = Field(..., min_length=1, description="Domain name (e.g., openai.com)")
    category: str = Field(..., min_length=1, description="Merchant category code or tag")
    is_whitelisted: bool = Field(default=True, description="Whether merchant is pre-cleared")


class PaymentIntentSchema(BaseModel):
    """Structured payment intent generated autonomously by agent in sandbox."""

    intent_id: str = Field(..., description="Unique intent ID")
    merchant: MerchantSpecSchema = Field(..., description="Target merchant")
    amount_cents: int = Field(..., ge=1, description="Amount in currency subunits")
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    line_items: list[str] = Field(default_factory=list, description="Purchased items")
    payment_rail: PaymentRailEnumResponse = Field(..., description="Selected payment rail")
    created_at: float = Field(..., description="Epoch creation timestamp")


class EphemeralPaymentTokenSchema(BaseModel):
    """Single-use ephemeral payment token minted by zero-knowledge financial vault."""

    token_id: str = Field(..., description="Token ID")
    intent_id: str = Field(..., description="Associated intent ID")
    masked_card_last4: str = Field(..., description="Virtual card suffix (e.g. 4242)")
    token_string: str = Field(..., description="Cryptographic single-use token string")
    max_amount_cents: int = Field(..., ge=1, description="Hard maximum authorization limit")
    expires_at: float = Field(..., description="Epoch expiry timestamp")
    is_consumed: bool = Field(default=False, description="Whether token has been settled")


class FinancialBudgetPolicySchema(BaseModel):
    """Enforceable multi-tier spend guardrails and hard caps."""

    daily_hard_cap_cents: int = Field(default=5000, ge=100, description="Daily spending ceiling in cents")
    single_transaction_max_cents: int = Field(default=2000, ge=100, description="Max amount per transaction")
    auto_approval_threshold_cents: int = Field(default=500, ge=0, description="Auto-approve limit without HITL")
    allowed_categories: list[str] = Field(
        default=[
            "cloud_compute",
            "api_credits",
            "e_books",
            "development_tools",
            "general_subscription",
        ],
        description="Allowed merchant categories",
    )


class SettlementReceiptSchema(BaseModel):
    """Immutable ledger receipt generated upon completed financial settlement."""

    receipt_id: str = Field(..., description="Ledger receipt unique ID")
    intent_id: str = Field(..., description="Associated payment intent ID")
    status: CommerceTransactionStatusResponse = Field(..., description="Final settlement status")
    amount_cents: int = Field(..., ge=1, description="Settled amount in cents")
    currency: str = Field(..., description="Currency code")
    merchant_name: str = Field(..., description="Settled merchant name")
    payment_rail: PaymentRailEnumResponse = Field(..., description="Settlement rail")
    confirmation_code: str = Field(..., description="Upstream gateway authorization code")
    settled_at: float = Field(..., description="Epoch settlement timestamp")


class CreatePaymentIntentRequest(BaseModel):
    """Payload to request an autonomous purchase intent evaluation."""

    merchant: MerchantSpecSchema = Field(..., description="Target merchant")
    amount_cents: int = Field(..., ge=1, description="Requested purchase amount in cents")
    currency: str = Field(default="USD", description="Currency code")
    line_items: list[str] = Field(default_factory=list, description="Itemized purchase lines")
    payment_rail: PaymentRailEnumResponse = Field(
        default=PaymentRailEnumResponse.STRIPE_AGENT_VIRTUAL_CARD,
        description="Desired payment rail",
    )


class CreatePaymentIntentResponse(BaseModel):
    """Evaluation result of payment intent by financial guardrail and vault."""

    intent: PaymentIntentSchema = Field(..., description="Structured payment intent")
    status: CommerceTransactionStatusResponse = Field(..., description="Guardrail decision")
    explanation: str = Field(..., description="Decision justification or HITL reason")
    token: EphemeralPaymentTokenSchema | None = Field(
        default=None,
        description="Single-use token if auto-approved, otherwise None",
    )


class ConfirmHITLRequest(BaseModel):
    """Payload to confirm pending HITL payment intent."""

    intent_id: str = Field(..., min_length=1, description="Payment intent ID to approve")


class ConfirmHITLResponse(BaseModel):
    """Result of user confirmation and token generation."""

    intent: PaymentIntentSchema = Field(..., description="Approved intent")
    token: EphemeralPaymentTokenSchema = Field(..., description="Newly minted single-use token")


class DenyHITLRequest(BaseModel):
    """Payload to reject pending HITL payment intent."""

    intent_id: str = Field(..., min_length=1, description="Payment intent ID to deny")


class DenyHITLResponse(BaseModel):
    """Result of user denial."""

    intent: PaymentIntentSchema = Field(..., description="Denied intent")
    message: str = Field(default="Transaction rejected by user operator.", description="Status note")


class SettleTransactionRequest(BaseModel):
    """Payload to settle charge using minted token."""

    token_string: str = Field(..., min_length=1, description="Single-use cryptographic token")
    intent: PaymentIntentSchema = Field(..., description="Payment intent being settled")


class BudgetStatusResponse(BaseModel):
    """Current financial budget and consumption metrics."""

    daily_hard_cap_cents: int = Field(..., ge=0, description="Daily cap limit")
    daily_spent_cents: int = Field(..., ge=0, description="Cumulative spend today")
    remaining_budget_cents: int = Field(..., ge=0, description="Remaining allowable spend")
    single_transaction_max_cents: int = Field(..., ge=0, description="Max single transaction ceiling")
    auto_approval_threshold_cents: int = Field(..., ge=0, description="Auto-approval threshold ceiling")


class UpdateBudgetPolicyRequest(BaseModel):
    """Payload to modify financial budget guardrails."""

    daily_hard_cap_cents: int = Field(default=5000, ge=100)
    single_transaction_max_cents: int = Field(default=2000, ge=100)
    auto_approval_threshold_cents: int = Field(default=500, ge=0)
    allowed_categories: list[str] = Field(
        default=[
            "cloud_compute",
            "api_credits",
            "e_books",
            "development_tools",
            "general_subscription",
        ]
    )


class CommerceMetricsResponse(BaseModel):
    """Cumulative operational metrics for commerce operations."""

    intents_created_total: int = Field(..., ge=0)
    auto_approved_total: int = Field(..., ge=0)
    hitl_approvals_requested_total: int = Field(..., ge=0)
    hitl_approved_total: int = Field(..., ge=0)
    hitl_denied_total: int = Field(..., ge=0)
    budget_rejections_total: int = Field(..., ge=0)
    settlements_completed_total: int = Field(..., ge=0)
    tokens_minted_total: int = Field(..., ge=0)
    total_spent_cents: int = Field(..., ge=0)
