"""Pydantic schemas for Autonomous Bot Asset Security Boundary and Wallet Air-Gap Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for financial transaction intents, spending ceiling policies,
  transaction evaluation verdicts, and two-person confirmation cards.

[POS]
- Server schemas. Exposes typed contracts for client UI and IM channels (Telegram/Feishu).
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class FinancialTransactionIntentDto(BaseModel):
    """Specification of an asset operation proposed by an Agent."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(..., description="Unique transaction proposal identifier")
    task_id: str = Field(..., description="Task or session ID originating this intent")
    action_type: str = Field(
        ..., description="Action classification: transfer, trade, swap, approve_allowance, buy, withdraw"
    )
    asset_symbol: str = Field(..., description="Target currency or token (e.g. USDC, ETH, SOL)")
    amount: float = Field(..., description="Asset nominal volume")
    estimated_usd_value: float = Field(..., description="Calculated USD market valuation")
    recipient_address: str = Field(..., description="Target counterparty address or contract")
    justification: str = Field(..., description="Analytical justification produced by Agent")


class TransactionEvaluationResponse(BaseModel):
    """Risk verdict on whether a transaction proposal may proceed autonomously or requires human sign-off."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(..., description="Evaluated intent ID")
    permitted_autonomous_execution: bool = Field(
        ..., description="True if allowed to execute without human intervention"
    )
    requires_human_confirmation: bool = Field(
        ..., description="True if threshold requires two-person verification card"
    )
    circuit_breaker_triggered: bool = Field(
        ..., description="True if daily spend limit was exceeded, halting execution"
    )
    current_daily_spend_usd: float = Field(..., description="Total USD spent today prior to or after transaction")
    remaining_daily_limit_usd: float = Field(..., description="Allowable USD limit remaining for current calendar day")
    reason: str = Field(..., description="Analytical rationale or circuit breaker warning")
    confirmation_card_id: str | None = Field(
        default=None, description="Generated confirmation card ID if human approval required"
    )


class SpendingCeilingPolicyDto(BaseModel):
    """Specification of risk thresholds for autonomous spend and circuit breakers."""

    model_config = ConfigDict(extra="forbid")

    daily_ceiling_usd: float = Field(50.0, description="Max cumulative USD spend allowed per day")
    single_transaction_ceiling_usd: float = Field(
        5.0, description="Max USD amount per individual autonomous transaction"
    )
    require_two_person_confirmation_above_usd: float = Field(
        5.0, description="Threshold above which human IM card confirmation is required"
    )
    allowed_asset_symbols: list[str] = Field(
        default_factory=lambda: ["USDC", "USDT", "ETH", "SOL", "BTC", "USD", "CNY"],
        description="Whitelisted asset symbols permitted for autonomous operations",
    )


class FinancialConfirmationCardDto(BaseModel):
    """Interactive card representation pushed to Telegram/Feishu channels for two-person signing."""

    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(..., description="Unique card identifier")
    intent: FinancialTransactionIntentDto = Field(..., description="Associated transaction intent details")
    status: str = Field(..., description="Lifecycle status: pending, approved, rejected, expired")
    created_at: float = Field(default_factory=time.time, description="Timestamp of card issuance")
    expires_at: float = Field(default_factory=lambda: time.time() + 300.0, description="Card expiration timestamp")


class DailySpendStatsDto(BaseModel):
    """Current asset expenditure metrics and headroom."""

    model_config = ConfigDict(extra="forbid")

    date_key: str = Field(..., description="Date key (YYYY-MM-DD)")
    current_spend_usd: float = Field(..., description="Cumulative USD expenditure today")
    remaining_limit_usd: float = Field(..., description="Remaining USD budget before circuit breaker trips")
    daily_ceiling_usd: float = Field(..., description="Total daily spending ceiling configured")
