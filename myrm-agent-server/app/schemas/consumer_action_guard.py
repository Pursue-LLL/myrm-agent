"""
[POS] app/schemas/consumer_action_guard.py
[INPUT] pydantic
[OUTPUT] ConsumerActionTypeEnum, ActionEvaluationVerdictEnum, ConsumerGuardPolicySchema, ConsumerOrderEvaluateRequest, ConsumerOrderEvaluateResponse, ConsumerOrderConfirmRequest, ConsumerOrderConfirmResponse, ConsumerGuardMetricsResponse

Pydantic schemas for Consumer-Grade Real-World Action Explosion and Velocity Limiter Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConsumerActionTypeEnum(StrEnum):
    """Categories of consumer real-world actions."""

    FOOD_DELIVERY = "FOOD_DELIVERY"
    GROCERY_PURCHASE = "GROCERY_PURCHASE"
    RIDE_HAILING = "RIDE_HAILING"
    TICKETING = "TICKETING"
    UTILITY_BILL = "UTILITY_BILL"
    GENERAL_RETAIL = "GENERAL_RETAIL"


class ActionEvaluationVerdictEnum(StrEnum):
    """Verdict on consumer order safety evaluation."""

    ALLOW_AUTONOMOUS = "ALLOW_AUTONOMOUS"
    REQUIRES_HUMAN_CONFIRMATION = "REQUIRES_HUMAN_CONFIRMATION"
    VELOCITY_RATE_LIMITED = "VELOCITY_RATE_LIMITED"
    DAILY_BUDGET_EXCEEDED = "DAILY_BUDGET_EXCEEDED"
    UNTRUSTED_ADDRESS_BLOCKED = "UNTRUSTED_ADDRESS_BLOCKED"


class ConsumerGuardPolicySchema(BaseModel):
    """Safety boundaries and invariant rules for an agent."""

    max_item_quantity: int = Field(default=5, ge=1, le=1000, description="Common-sense single item quantity ceiling.")
    max_single_action_amount: float = Field(default=100.0, ge=0.0, description="Max amount for autonomous approval.")
    velocity_window_seconds: float = Field(default=900.0, ge=1.0, description="Sliding window duration in seconds.")
    max_actions_per_window: int = Field(default=1, ge=1, le=100, description="Max allowed orders per sliding window.")
    daily_spend_ceiling: float = Field(default=200.0, ge=0.0, description="Daily rolling 24h spending ceiling.")
    allowlisted_addresses: list[str] = Field(default_factory=list, description="Safe delivery addresses.")
    allowlisted_phones: list[str] = Field(default_factory=list, description="Safe recipient phone numbers.")
    allowlisted_merchants: list[str] = Field(default_factory=list, description="Approved merchant identifiers.")


class ConsumerOrderEvaluateRequest(BaseModel):
    """Payload to evaluate an outbound consumer order against guardrails."""

    order_id: str = Field(..., min_length=1, max_length=128, description="Unique order identifier.")
    agent_id: str = Field(..., min_length=1, max_length=128, description="Executing agent ID.")
    action_type: ConsumerActionTypeEnum = Field(..., description="Action classification.")
    item_name: str = Field(..., min_length=1, max_length=256, description="Product or service name.")
    quantity: int = Field(..., ge=1, description="Quantity of items being ordered.")
    unit_price: float = Field(..., ge=0.0, description="Price per unit.")
    total_amount: float = Field(..., ge=0.0, description="Total order amount.")
    recipient_name: str = Field(..., min_length=1, max_length=128, description="Recipient name.")
    recipient_phone: str = Field(..., min_length=1, max_length=64, description="Contact phone.")
    delivery_address: str = Field(..., min_length=1, max_length=512, description="Physical delivery destination.")
    merchant_id: str = Field(..., min_length=1, max_length=128, description="Merchant or vendor identifier.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags.")


class ConsumerOrderEvaluateResponse(BaseModel):
    """Safety evaluation outcome on consumer action."""

    is_allowed: bool = Field(..., description="True if order satisfies all automated safety assertions.")
    verdict: ActionEvaluationVerdictEnum = Field(..., description="Safety verdict.")
    message: str = Field(..., description="Detailed explanation.")
    requires_hitl: bool = Field(..., description="True if order must be approved manually by human user.")
    confirmation_card_summary: str | None = Field(default=None, description="Grandma-proof UI confirmation card.")


class ConsumerOrderConfirmRequest(BaseModel):
    """Payload to record and confirm an executed consumer order."""

    order_id: str = Field(..., min_length=1, description="Order identifier.")
    agent_id: str = Field(..., min_length=1, description="Executing agent ID.")
    action_type: ConsumerActionTypeEnum = Field(..., description="Action category.")
    total_amount: float = Field(..., ge=0.0, description="Confirmed order total amount.")


class ConsumerOrderConfirmResponse(BaseModel):
    """Confirmation receipt of recorded order."""

    order_id: str = Field(..., description="Order identifier.")
    agent_id: str = Field(..., description="Agent ID.")
    is_confirmed: bool = Field(..., description="Confirmation flag.")
    current_daily_spent: float = Field(..., description="Updated rolling 24h spend total.")


class ConsumerGuardMetricsResponse(BaseModel):
    """Telemetry counters for consumer protection subsystem."""

    total_evaluations: int = Field(..., ge=0, description="Total evaluations performed.")
    autonomous_approvals: int = Field(..., ge=0, description="Orders allowed without human intervention.")
    hitl_confirmations_required: int = Field(..., ge=0, description="Orders requiring human confirmation.")
    velocity_blocks: int = Field(..., ge=0, description="Orders blocked due to velocity rate limiting.")
    budget_exceeded_blocks: int = Field(..., ge=0, description="Orders blocked due to daily budget ceiling.")
    address_blocks: int = Field(..., ge=0, description="Orders blocked due to untrusted destination.")
