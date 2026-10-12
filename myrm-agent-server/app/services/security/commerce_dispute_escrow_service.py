"""Service layer for Agent Commerce Dispute & Escrow management.

[INPUT]
- myrm_agent_harness.core.security.commerce_dispute_escrow::CommerceEscrowManager (POS: Lifecycle manager handling commitments and disputes)
- app.schemas.commerce_dispute_escrow::CreateEscrowRequest (POS: Schema for creating escrow accounts)

[OUTPUT]
- CommerceDisputeEscrowService: Governs commercial escrow, commit-reveal arbitration, and trading circuit breakers.

[POS]
Service layer bridging commerce escrow lifecycle and multi-seat dispute arbitration to FastAPI routers.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.commerce_dispute_escrow import (
    CommerceEscrowManager,
    DisputeCase,
    EscrowAccount,
    StrategyType,
    TradingCircuitBreakers,
)

from app.schemas.commerce_dispute_escrow import (
    ArbitratorVoteDto,
    CircuitBreakerEvaluationResponse,
    CommitArbitratorVoteRequest,
    CreateEscrowRequest,
    DisputeCaseDto,
    DisputeSettlementResponse,
    EscrowAccountDto,
    EvaluateCircuitBreakerRequest,
    RaiseDisputeRequest,
    ReleaseFundsRequest,
    RevealArbitratorVoteRequest,
    SubmitDeliverableRequest,
    TradingCircuitBreakersDto,
)

logger = logging.getLogger(__name__)


class CommerceDisputeEscrowService:
    """Service governing commercial escrow and multi-seat arbitration."""

    def __init__(self, manager: CommerceEscrowManager | None = None) -> None:
        """Initialize service with core manager."""
        self._manager = manager or CommerceEscrowManager()

    def create_escrow(self, request: CreateEscrowRequest) -> EscrowAccountDto:
        """Create and fund a new escrow account."""
        logger.info(
            "Creating escrow for job '%s' with amount %s",
            request.job_id,
            request.amount,
        )
        breakers: TradingCircuitBreakers | None = None
        if request.circuit_breakers:
            breakers = TradingCircuitBreakers(
                max_position_pct=request.circuit_breakers.max_position_pct,
                max_daily_loss_pct=request.circuit_breakers.max_daily_loss_pct,
                max_open_exposure_pct=request.circuit_breakers.max_open_exposure_pct,
                emergency_kill_switch_active=request.circuit_breakers.emergency_kill_switch_active,
            )

        escrow = self._manager.create_escrow(
            job_id=request.job_id,
            client_agent_id=request.client_agent_id,
            provider_agent_id=request.provider_agent_id,
            strategy_type=StrategyType(request.strategy_type),
            amount=request.amount,
            circuit_breakers=breakers,
        )
        return self._to_escrow_dto(escrow)

    def get_escrow(self, escrow_id: str) -> EscrowAccountDto:
        """Retrieve escrow details."""
        escrow = self._manager.get_escrow(escrow_id)
        return self._to_escrow_dto(escrow)

    def submit_deliverable(self, request: SubmitDeliverableRequest) -> EscrowAccountDto:
        """Register completed deliverable proof."""
        logger.info("Submitting deliverable for escrow '%s'", request.escrow_id)
        escrow = self._manager.submit_deliverable(
            escrow_id=request.escrow_id,
            provider_agent_id=request.provider_agent_id,
            deliverable_hash=request.deliverable_hash,
        )
        return self._to_escrow_dto(escrow)

    def release_funds(self, request: ReleaseFundsRequest) -> EscrowAccountDto:
        """Authorize fund release to provider."""
        logger.info(
            "Releasing funds for escrow '%s' by client '%s'",
            request.escrow_id,
            request.client_agent_id,
        )
        escrow = self._manager.release_funds(
            escrow_id=request.escrow_id,
            client_agent_id=request.client_agent_id,
        )
        return self._to_escrow_dto(escrow)

    def evaluate_circuit_breaker(
        self, request: EvaluateCircuitBreakerRequest
    ) -> CircuitBreakerEvaluationResponse:
        """Evaluate circuit breaker conditions."""
        triggered, reason = self._manager.evaluate_circuit_breaker(
            escrow_id=request.escrow_id,
            current_position_pct=request.current_position_pct,
            current_daily_loss_pct=request.current_daily_loss_pct,
            current_open_exposure_pct=request.current_open_exposure_pct,
            emergency_trigger=request.emergency_trigger,
        )
        escrow = self._manager.get_escrow(request.escrow_id)
        return CircuitBreakerEvaluationResponse(
            triggered=triggered,
            reason=reason,
            escrow_status=escrow.status.value,
        )

    def raise_dispute(self, request: RaiseDisputeRequest) -> DisputeCaseDto:
        """Initiate multi-seat arbitration dispute."""
        logger.info(
            "Raising dispute for escrow '%s' by '%s'",
            request.escrow_id,
            request.initiator_agent_id,
        )
        dispute = self._manager.raise_dispute(
            escrow_id=request.escrow_id,
            initiator_agent_id=request.initiator_agent_id,
            deposit_amount=request.deposit_amount,
            arbitrators=request.arbitrators,
        )
        return self._to_dispute_dto(dispute)

    def get_dispute(self, dispute_id: str) -> DisputeCaseDto:
        """Retrieve dispute details."""
        dispute = self._manager.get_dispute(dispute_id)
        return self._to_dispute_dto(dispute)

    def commit_vote(self, request: CommitArbitratorVoteRequest) -> DisputeCaseDto:
        """Commit arbitrator vote hash."""
        dispute = self._manager.commit_vote(
            dispute_id=request.dispute_id,
            seat_index=request.seat_index,
            arbitrator_id=request.arbitrator_id,
            commitment_hash=request.commitment_hash,
        )
        return self._to_dispute_dto(dispute)

    def reveal_vote(self, request: RevealArbitratorVoteRequest) -> DisputeCaseDto:
        """Reveal committed arbitrator vote."""
        dispute = self._manager.reveal_vote(
            dispute_id=request.dispute_id,
            seat_index=request.seat_index,
            arbitrator_id=request.arbitrator_id,
            vote=request.vote,
            salt=request.salt,
        )
        return self._to_dispute_dto(dispute)

    def settle_dispute(self, dispute_id: str) -> DisputeSettlementResponse:
        """Settle dispute and distribute funds."""
        logger.info("Settling dispute '%s'", dispute_id)
        dispute, escrow, settlement = self._manager.settle_dispute(dispute_id)
        return DisputeSettlementResponse(
            dispute=self._to_dispute_dto(dispute),
            escrow=self._to_escrow_dto(escrow),
            refund_to_client=settlement.refund_to_client,
            release_to_provider=settlement.release_to_provider,
            deposit_refunded=settlement.deposit_refunded,
            arbitrator_fee_pool=settlement.arbitrator_fee_pool,
        )

    @staticmethod
    def _to_escrow_dto(escrow: EscrowAccount) -> EscrowAccountDto:
        breakers_dto: TradingCircuitBreakersDto | None = None
        if escrow.circuit_breakers:
            breakers_dto = TradingCircuitBreakersDto(
                max_position_pct=escrow.circuit_breakers.max_position_pct,
                max_daily_loss_pct=escrow.circuit_breakers.max_daily_loss_pct,
                max_open_exposure_pct=escrow.circuit_breakers.max_open_exposure_pct,
                emergency_kill_switch_active=(
                    escrow.circuit_breakers.emergency_kill_switch_active
                ),
            )
        return EscrowAccountDto(
            escrow_id=escrow.escrow_id,
            job_id=escrow.job_id,
            client_agent_id=escrow.client_agent_id,
            provider_agent_id=escrow.provider_agent_id,
            strategy_type=escrow.strategy_type.value,
            amount=escrow.amount,
            status=escrow.status.value,
            deliverable_hash=escrow.deliverable_hash,
            circuit_breakers=breakers_dto,
            created_at=escrow.created_at,
            updated_at=escrow.updated_at,
        )

    @staticmethod
    def _to_dispute_dto(dispute: DisputeCase) -> DisputeCaseDto:
        return DisputeCaseDto(
            dispute_id=dispute.dispute_id,
            escrow_id=dispute.escrow_id,
            initiator_agent_id=dispute.initiator_agent_id,
            deposit_amount=dispute.deposit_amount,
            status=dispute.status.value,
            votes=[
                ArbitratorVoteDto(
                    seat_index=v.seat_index,
                    arbitrator_id=v.arbitrator_id,
                    commitment_hash=v.commitment_hash,
                    revealed_vote=v.revealed_vote,
                    revealed_at=v.revealed_at,
                )
                for v in dispute.votes
            ],
            outcome=dispute.outcome.value,
            settled_at=dispute.settled_at,
        )


_service_instance: CommerceDisputeEscrowService | None = None


def get_commerce_dispute_escrow_service() -> CommerceDisputeEscrowService:
    """Dependency injection provider for CommerceDisputeEscrowService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CommerceDisputeEscrowService()
    return _service_instance
