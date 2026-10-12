"""Pydantic schemas for Agent Commerce Dispute & Escrow management.

[INPUT]
- Web requests managing autonomous agent escrows, deliverable proofs, disputes, and circuit breakers.

[OUTPUT]
- Serialized escrow statuses, multi-seat arbitration states, and settlement financial distributions.

[POS]
- Server-side DTO contracts for TermiX-aligned commercial escrow and dispute governance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TradingCircuitBreakersDto(BaseModel):
    """Quantitative risk thresholds and circuit breaker configuration."""

    max_position_pct: float = Field(
        default=25.0, description="Max single position size percentage"
    )
    max_daily_loss_pct: float = Field(
        default=10.0, description="Max allowed daily drawdown percentage"
    )
    max_open_exposure_pct: float = Field(
        default=50.0, description="Max total capital exposure percentage"
    )
    emergency_kill_switch_active: bool = Field(
        default=False, description="Emergency kill switch toggle"
    )


class CreateEscrowRequest(BaseModel):
    """Request payload to create and fund a commercial escrow account."""

    job_id: str = Field(description="Unique commercial job identifier")
    client_agent_id: str = Field(description="Funding client agent identifier")
    provider_agent_id: str = Field(description="Contracted provider agent identifier")
    strategy_type: Literal["PROGRAM", "RUBRIC", "HYBRID", "CEX_CAPITAL"] = Field(
        description="Execution strategy type"
    )
    amount: float = Field(gt=0, description="Escrowed capital amount in USDC")
    circuit_breakers: TradingCircuitBreakersDto | None = Field(
        default=None, description="Optional trading circuit breakers for capital jobs"
    )


class SubmitDeliverableRequest(BaseModel):
    """Payload to submit on-chain proof or hash for deliverable."""

    escrow_id: str = Field(description="Escrow account identifier")
    provider_agent_id: str = Field(description="Assigned provider agent identifier")
    deliverable_hash: str = Field(description="Cryptographic proof or artifact hash")


class ReleaseFundsRequest(BaseModel):
    """Payload to authorize release of escrow funds to provider."""

    escrow_id: str = Field(description="Escrow account identifier")
    client_agent_id: str = Field(description="Client agent identifier")


class EvaluateCircuitBreakerRequest(BaseModel):
    """Payload to test risk metrics against circuit breakers."""

    escrow_id: str = Field(description="Escrow account identifier")
    current_position_pct: float = Field(default=0.0)
    current_daily_loss_pct: float = Field(default=0.0)
    current_open_exposure_pct: float = Field(default=0.0)
    emergency_trigger: bool = Field(default=False)


class CircuitBreakerEvaluationResponse(BaseModel):
    """Result of evaluating trading risk metrics."""

    triggered: bool = Field(description="Whether a circuit breaker was tripped")
    reason: str | None = Field(default=None, description="Trigger reason if tripped")
    escrow_status: str = Field(description="Updated escrow status")


class RaiseDisputeRequest(BaseModel):
    """Payload to initiate formal arbitration dispute."""

    escrow_id: str = Field(description="Escrow account identifier")
    initiator_agent_id: str = Field(description="Disputing agent identifier")
    deposit_amount: float | None = Field(
        default=None, description="Dispute deposit amount (min 5% of escrow)"
    )
    arbitrators: list[str] | None = Field(
        default=None, description="Optional list of 3 designated arbitrator IDs"
    )


class CommitArbitratorVoteRequest(BaseModel):
    """Payload to submit hash commitment for arbitrator vote."""

    dispute_id: str = Field(description="Dispute case identifier")
    seat_index: int = Field(ge=0, le=2, description="Arbitrator seat index (0-2)")
    arbitrator_id: str = Field(description="Assigned arbitrator identifier")
    commitment_hash: str = Field(description="SHA-256 hash of vote:salt")


class RevealArbitratorVoteRequest(BaseModel):
    """Payload to reveal committed vote and salt."""

    dispute_id: str = Field(description="Dispute case identifier")
    seat_index: int = Field(ge=0, le=2, description="Arbitrator seat index (0-2)")
    arbitrator_id: str = Field(description="Assigned arbitrator identifier")
    vote: int = Field(ge=0, le=1, description="Vote decision: 0=uphold, 1=overturn")
    salt: str = Field(description="Salt used during commitment")


class ArbitratorVoteDto(BaseModel):
    """Arbitration seat state."""

    seat_index: int
    arbitrator_id: str
    commitment_hash: str | None = None
    revealed_vote: int | None = None
    revealed_at: float | None = None


class EscrowAccountDto(BaseModel):
    """Serialized escrow account details."""

    escrow_id: str
    job_id: str
    client_agent_id: str
    provider_agent_id: str
    strategy_type: str
    amount: float
    status: str
    deliverable_hash: str | None = None
    circuit_breakers: TradingCircuitBreakersDto | None = None
    created_at: float
    updated_at: float


class DisputeCaseDto(BaseModel):
    """Serialized dispute case details."""

    dispute_id: str
    escrow_id: str
    initiator_agent_id: str
    deposit_amount: float
    status: str
    votes: list[ArbitratorVoteDto]
    outcome: str
    settled_at: float | None = None


class DisputeSettlementResponse(BaseModel):
    """Settlement outcome and financial distribution."""

    dispute: DisputeCaseDto
    escrow: EscrowAccountDto
    refund_to_client: float
    release_to_provider: float
    deposit_refunded: float
    arbitrator_fee_pool: float
