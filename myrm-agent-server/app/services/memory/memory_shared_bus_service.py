"""
[POS] app/services/memory/memory_shared_bus_service.py
[INPUT] app.schemas.memory_shared_bus, myrm_agent_harness.toolkits.memory.shared_bus
[OUTPUT] MemorySharedBusService, get_memory_shared_bus_service

Service coordinating the Multi-Agent Shared Memory Bus, Concurrency Pool, Backpressure Guard, and Negative Decision Ledger.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.shared_bus import (
    BackpressureStatus,
    ConcurrencyPoolConfig,
    DecisionVetoSeverity,
    MultiAgentSharedMemoryBus,
    NegativeDecisionCheckResult,
    NegativeDecisionEntry,
    ReinforcedDecayConfig,
    ScoredMemoryItem,
)

from app.schemas.memory_shared_bus import (
    ConcurrencyPoolStatusResponseDTO,
    MemoryScoreRequestDTO,
    MemoryScoreResponseDTO,
    NegativeDecisionCheckRequestDTO,
    NegativeDecisionCheckResponseDTO,
    NegativeDecisionCreateRequestDTO,
    NegativeDecisionDTO,
)


def _to_harness_entry(dto: NegativeDecisionCreateRequestDTO) -> NegativeDecisionEntry:
    """Convert API request to harness NegativeDecisionEntry."""
    severity = DecisionVetoSeverity.HARD_BLOCK
    try:
        severity = DecisionVetoSeverity(dto.severity.lower())
    except ValueError:
        pass

    return NegativeDecisionEntry(
        decision_id=dto.decision_id,
        decision_subject=dto.decision_subject,
        veto_reason=dto.veto_reason,
        alternative_chosen=dto.alternative_chosen,
        context_summary=dto.context_summary,
        severity=severity,
        scope=dto.scope,
    )


def _to_dto_entry(harness: NegativeDecisionEntry) -> NegativeDecisionDTO:
    """Convert harness NegativeDecisionEntry to API NegativeDecisionDTO."""
    return NegativeDecisionDTO(
        decision_id=harness.decision_id,
        decision_subject=harness.decision_subject,
        veto_reason=harness.veto_reason,
        alternative_chosen=harness.alternative_chosen,
        context_summary=harness.context_summary,
        severity=str(harness.severity.value),
        scope=harness.scope,
        created_at=harness.created_at,
    )


def _to_dto_check_response(
    result: NegativeDecisionCheckResult,
) -> NegativeDecisionCheckResponseDTO:
    """Convert harness check result to API response DTO."""
    return NegativeDecisionCheckResponseDTO(
        is_blocked=result.is_blocked,
        matched_entries=[_to_dto_entry(e) for e in result.matched_entries],
        guard_prompt_slice=result.guard_prompt_slice,
        rejection_summary=result.rejection_summary,
    )


def _to_dto_pool_status(status: BackpressureStatus) -> ConcurrencyPoolStatusResponseDTO:
    """Convert harness backpressure status to API response DTO."""
    return ConcurrencyPoolStatusResponseDTO(
        active_readers=status.active_readers,
        active_writers=status.active_writers,
        queued_tasks=status.queued_tasks,
        current_rss_mb=round(status.current_rss_mb, 2),
        is_throttled=status.is_throttled,
        status_message=status.status_message,
    )


def _to_dto_scored_response(item: ScoredMemoryItem) -> MemoryScoreResponseDTO:
    """Convert scored memory item to API response DTO."""
    return MemoryScoreResponseDTO(
        memory_id=item.memory_id,
        content=item.content,
        base_weight=item.base_weight,
        hit_count=item.hit_count,
        last_accessed_at=item.last_accessed_at,
        composite_score=item.composite_score,
        decay_factor=item.decay_factor,
        reinforcement_factor=item.reinforcement_factor,
    )


class MemorySharedBusService:
    """Service wrapping MultiAgentSharedMemoryBus for server operations."""

    def __init__(
        self,
        pool_config: ConcurrencyPoolConfig | None = None,
        decay_config: ReinforcedDecayConfig | None = None,
    ) -> None:
        self._bus = MultiAgentSharedMemoryBus(
            pool_config=pool_config, decay_config=decay_config
        )

    @property
    def bus(self) -> MultiAgentSharedMemoryBus:
        """Direct accessor for the underlying harness bus."""
        return self._bus

    def record_veto(self, request: NegativeDecisionCreateRequestDTO) -> NegativeDecisionDTO:
        """Record a vetoed technical decision into the ledger."""
        entry = _to_harness_entry(request)
        self._bus.record_veto(entry)
        return _to_dto_entry(entry)

    def check_veto(
        self, request: NegativeDecisionCheckRequestDTO
    ) -> NegativeDecisionCheckResponseDTO:
        """Screen a candidate proposal against historical vetoes."""
        result = self._bus.check_proposal(
            proposal=request.candidate_proposal,
            scope=request.scope,
        )
        return _to_dto_check_response(result)

    def list_vetoes(self, scope: str | None = None) -> list[NegativeDecisionDTO]:
        """List active veto records."""
        entries = self._bus.list_vetoes(scope=scope)
        return [_to_dto_entry(e) for e in entries]

    def get_pool_status(self) -> ConcurrencyPoolStatusResponseDTO:
        """Query real-time pool concurrency and memory backpressure metrics."""
        status = self._bus.get_pool_status()
        return _to_dto_pool_status(status)

    def score_memory(self, request: MemoryScoreRequestDTO) -> MemoryScoreResponseDTO:
        """Evaluate self-learning composite score combining frequency and decay."""
        scored = self._bus.score_memory(
            memory_id=request.memory_id,
            content=request.content,
            base_weight=request.base_weight,
            hit_count=request.hit_count,
            last_accessed_at=request.last_accessed_at,
        )
        return _to_dto_scored_response(scored)


_shared_bus_service_instance: MemorySharedBusService | None = None


def get_memory_shared_bus_service() -> MemorySharedBusService:
    """Singleton getter for MemorySharedBusService."""
    global _shared_bus_service_instance
    if _shared_bus_service_instance is None:
        _shared_bus_service_instance = MemorySharedBusService()
    return _shared_bus_service_instance
