# [POS]: app/services/memory/dialectic_guard_service.py
# [INPUT]: app.schemas.dialectic_guard, myrm_agent_harness.toolkits.memory
# [OUTPUT]: DialecticGuardService, get_dialectic_guard_service

"""Business service implementing Dialectic Liveness Guard & Stale Pivot Discard (Item 116)."""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    DialecticLivenessAuditLog,
    DialecticLivenessConfig,
    DialecticLivenessStateMachine,
    LivenessTelemetry,
)

from app.schemas.dialectic_guard import (
    ConsumePendingRequest,
    ConsumePendingResponse,
    DialecticAuditLogDTO,
    DialecticLivenessConfigDTO,
    LivenessTelemetryDTO,
    NotifyMutationRequest,
    NotifyMutationResponse,
    ShouldTriggerRequest,
    ShouldTriggerResponse,
    SubmitResultRequest,
    SubmitResultResponse,
)

logger = logging.getLogger(__name__)


def _audit_to_dto(log: DialecticLivenessAuditLog) -> DialecticAuditLogDTO:
    """Map internal domain audit log to API DTO."""
    return DialecticAuditLogDTO(
        event_id=log.event_id,
        session_id=log.session_id,
        action=log.action,
        turn=log.turn,
        detail=log.detail,
        timestamp_monotonic=log.timestamp_monotonic,
    )


def _telemetry_to_dto(tel: LivenessTelemetry) -> LivenessTelemetryDTO:
    """Map internal domain telemetry to API DTO."""
    return LivenessTelemetryDTO(
        session_id=tel.session_id,
        current_turn=tel.current_turn,
        effective_cadence=tel.effective_cadence,
        empty_streak=tel.empty_streak,
        slot_state=tel.slot_state,
        active_cycle_token=tel.active_cycle_token,
        total_fires=tel.total_fires,
        dead_threads_recovered=tel.dead_threads_recovered,
        stale_pivots_discarded=tel.stale_pivots_discarded,
        stale_tokens_rejected=tel.stale_tokens_rejected,
        successful_consumptions=tel.successful_consumptions,
        audit_events=[_audit_to_dto(x) for x in tel.audit_events],
    )


def _dto_to_config(dto: DialecticLivenessConfigDTO | None) -> DialecticLivenessConfig:
    """Map optional configuration DTO to internal domain configuration."""
    if dto is None:
        return DialecticLivenessConfig()
    return DialecticLivenessConfig(
        base_cadence=dto.base_cadence,
        timeout_seconds=dto.timeout_seconds,
        stale_thread_multiplier=dto.stale_thread_multiplier,
        stale_result_multiplier=dto.stale_result_multiplier,
        max_backoff_multiplier=dto.max_backoff_multiplier,
    )


class DialecticGuardService:
    """Domain service managing background dialectic inference liveness and pivot invalidation."""

    def __init__(self, state_machine: DialecticLivenessStateMachine | None = None) -> None:
        self._state_machine = state_machine or DialecticLivenessStateMachine()

    def should_trigger(self, req: ShouldTriggerRequest) -> ShouldTriggerResponse:
        """Evaluate if dialectic inference cycle should trigger."""
        triggered, token = self._state_machine.should_trigger(
            session_id=req.session_id,
            current_turn=req.current_turn,
            now_mono=req.now_mono,
        )
        effective_cadence = self._state_machine.get_effective_cadence(req.session_id)
        return ShouldTriggerResponse(
            should_trigger=triggered,
            cycle_token=token,
            effective_cadence=effective_cadence,
        )

    def submit_result(self, req: SubmitResultRequest) -> SubmitResultResponse:
        """Submit background inference result, guarding against orphan zombie returns."""
        accepted = self._state_machine.submit_result(
            session_id=req.session_id,
            cycle_token=req.cycle_token,
            content=req.content,
            now_mono=req.now_mono,
        )
        staged = accepted and bool(req.content and req.content.strip())
        return SubmitResultResponse(
            accepted=accepted,
            staged=staged,
        )

    def consume_pending_result(self, req: ConsumePendingRequest) -> ConsumePendingResponse:
        """Consume staged dialectic result or discard it if conversational pivot occurred."""
        content = self._state_machine.consume_pending_result(
            session_id=req.session_id,
            current_turn=req.current_turn,
        )
        return ConsumePendingResponse(
            has_content=content is not None,
            content=content,
        )

    def notify_mutation(self, req: NotifyMutationRequest) -> NotifyMutationResponse:
        """Reset exponential backoff on critical mutation event."""
        self._state_machine.notify_critical_mutation(
            session_id=req.session_id,
            reason=req.reason,
        )
        effective = self._state_machine.get_effective_cadence(req.session_id)
        return NotifyMutationResponse(
            success=True,
            effective_cadence=effective,
        )

    def get_telemetry(self, session_id: str, current_turn: int) -> LivenessTelemetryDTO:
        """Retrieve liveness telemetry snapshot."""
        tel = self._state_machine.get_telemetry(session_id, current_turn)
        return _telemetry_to_dto(tel)

    def get_audit_logs(self, session_id: str) -> list[DialecticAuditLogDTO]:
        """Retrieve audit history for a session."""
        logs = self._state_machine.get_audit_logs(session_id)
        return [_audit_to_dto(x) for x in logs]


@lru_cache(maxsize=1)
def get_dialectic_guard_service() -> DialecticGuardService:
    """Return the singleton instance of DialecticGuardService."""
    return DialecticGuardService()
