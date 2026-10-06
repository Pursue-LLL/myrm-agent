"""Pydantic schemas for Autonomous Financial Execution Safety Guard and Simulation Suite.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- TransactionIntentRequest, TransactionSecurityCardResponse, ApproveTransactionRequest
- BudgetConfigUpdateRequest, BudgetStatusResponse

[POS]
Schema definitions for autonomous financial safety guard, transaction evaluation, and budgets.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransactionIntentRequest(BaseModel):
    """Payload representing a proposed financial transaction intent."""

    tx_id: str = Field(..., description="Unique transaction identifier")
    source_account: str = Field(..., description="Sender account or wallet address")
    target_contract_or_recipient: str = Field(..., description="Target contract or recipient address")
    asset_symbol: str = Field(..., description="Asset symbol, e.g. USDT, ETH, SOL")
    amount: float = Field(..., description="Asset native nominal amount")
    amount_usd: float = Field(..., description="USD equivalent value of the transaction")
    slippage_tolerance_bps: int = Field(
        default=50,
        description="User configured slippage tolerance in basis points (100 bps = 1%)",
    )
    max_fee_limit: float = Field(
        default=5.0,
        description="Maximum acceptable fee/gas in USD",
    )
    payload_digest: str = Field(
        default="",
        description="Deterministic cryptographic digest of raw transaction payload",
    )


class SimulationResultResponse(BaseModel):
    """Sandbox simulation and market depth impact outcomes."""

    is_simulated: bool = Field(..., description="Whether transaction was dry-run simulated")
    estimated_gas_or_fee: float = Field(..., description="Estimated network gas or transaction fee in USD")
    estimated_slippage_bps: int = Field(..., description="Simulated execution slippage in basis points")
    max_loss_usd: float = Field(..., description="Theoretical worst-case principal downside in USD")
    risk_score: int = Field(..., description="Composite risk score from 0 (safest) to 100 (critical)")
    simulation_notes: list[str] = Field(
        default_factory=list,
        description="Descriptive simulation diagnosis and notes",
    )


class TransactionSecurityCardResponse(BaseModel):
    """Structured security card and audit verification dossier."""

    tx_id: str = Field(..., description="Unique transaction identifier")
    decision: str = Field(..., description="Evaluation decision: APPROVE, ASK_CONFIRMATION, or REJECT_BREAKER")
    risk_tier: str = Field(..., description="Risk tier: LOW, MEDIUM, HIGH, or CRITICAL")
    intent: TransactionIntentRequest = Field(..., description="Original transaction intent")
    simulation: SimulationResultResponse = Field(..., description="Simulation findings")
    daily_spent_usd: float = Field(..., description="Total spent USD today within the current window")
    remaining_daily_budget_usd: float = Field(..., description="Remaining uncommitted USD budget today")
    requires_manual_approval: bool = Field(..., description="Whether manual physical confirmation is required")
    rejection_reason: str | None = Field(default=None, description="Explanation if rejected or suspended")
    created_at: float = Field(..., description="Timestamp of evaluation")


class BudgetConfigUpdateRequest(BaseModel):
    """Payload to update spending and circuit breaker thresholds."""

    single_tx_limit_usd: float | None = Field(default=None, description="Max auto-approved single tx USD limit")
    daily_limit_usd: float | None = Field(default=None, description="Max daily cumulative expenditure limit in USD")
    max_allowed_slippage_bps: int | None = Field(default=None, description="Max allowed slippage before circuit trip")
    critical_risk_score_threshold: int | None = Field(default=None, description="Risk score threshold to auto-reject")


class BudgetStatusResponse(BaseModel):
    """Current budget, expenditure, and circuit breaker configuration status."""

    single_tx_limit_usd: float = Field(..., description="Single transaction auto-approval limit in USD")
    daily_limit_usd: float = Field(..., description="Daily total spending limit in USD")
    daily_spent_usd: float = Field(..., description="Accumulated spending today in USD")
    remaining_daily_budget_usd: float = Field(..., description="Remaining available spending budget in USD")
    max_allowed_slippage_bps: int = Field(..., description="Maximum allowed slippage before breaker trip")
    critical_risk_score_threshold: int = Field(..., description="Risk score cutoff threshold")


class ApproveTransactionRequest(BaseModel):
    """Request to manually authorize a transaction suspended for confirmation."""

    tx_id: str = Field(..., description="Transaction ID to approve")
