"""
[POS] app/services/agent/agent_handoff_service.py
[INPUT] pathlib.Path, app/schemas/agent_handoff.py, myrm_agent_harness.agent.context_management.handoff
[OUTPUT] AgentHandoffService, get_agent_handoff_service

Service layer governing typed cross-agent handoff memorandum persistence, CAS claim, and lifecycle state.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from myrm_agent_harness.agent.context_management.handoff import (
    AgentHandoffEngine,
    AgentHandoffSpec,
    FailedApproachRecord,
    FinalizeSessionRequest,
    FinalizeSessionResult,
    HandoffClaimReceipt,
    ImplicitConstraintRecord,
)

from app.schemas.agent_handoff import (
    AgentHandoffSpecDTO,
    CancelHandoffRequestDTO,
    ClaimHandoffRequestDTO,
    CompleteHandoffRequestDTO,
    FailedApproachDTO,
    FinalizeSessionRequestDTO,
    FinalizeSessionResponseDTO,
    HandoffClaimReceiptDTO,
    HandoffListResponseDTO,
    ImplicitConstraintDTO,
)


def _spec_to_dto(spec: AgentHandoffSpec) -> AgentHandoffSpecDTO:
    """Transform internal Harness AgentHandoffSpec to public API DTO."""
    return AgentHandoffSpecDTO(
        handoff_id=spec.handoff_id,
        session_id=spec.session_id,
        source_profile_id=spec.source_profile_id,
        target_profile_id=spec.target_profile_id,
        active_goal=spec.active_goal,
        failed_approaches=[
            FailedApproachDTO(
                approach_name=fa.approach_name,
                rejected_reason=fa.rejected_reason,
                evidence_snippet=fa.evidence_snippet,
                attempted_by_profile_id=fa.attempted_by_profile_id,
            )
            for fa in spec.failed_approaches
        ],
        implicit_constraints=[
            ImplicitConstraintDTO(
                scope=ic.scope,
                constraint_rule=ic.constraint_rule,
                rationale=ic.rationale,
            )
            for ic in spec.implicit_constraints
        ],
        errors_and_fixes=list(spec.errors_and_fixes),
        pending_asks=list(spec.pending_asks),
        next_actions=list(spec.next_actions),
        status=spec.status.value,
        created_at=spec.created_at,
        claimed_at=spec.claimed_at,
        claimed_by_profile_id=spec.claimed_by_profile_id,
        claimed_by_session_id=spec.claimed_by_session_id,
        completed_at=spec.completed_at,
    )


class AgentHandoffService:
    """Business service wrapping the underlying AgentHandoffEngine facade."""

    def __init__(self, engine: AgentHandoffEngine | None = None) -> None:
        if engine is not None:
            self._engine = engine
        else:
            base_dir_env = os.getenv("MYRM_AGENT_HANDOFF_DIR", ".myrm/handoffs")
            storage_dir = Path(base_dir_env).resolve()
            self._engine = AgentHandoffEngine(storage_dir=storage_dir)

    def finalize_session(self, req: FinalizeSessionRequestDTO) -> FinalizeSessionResponseDTO:
        """Finalize working session and write durable handoff memorandum."""
        harness_req = FinalizeSessionRequest(
            session_id=req.session_id,
            source_profile_id=req.source_profile_id,
            target_profile_id=req.target_profile_id,
            active_goal=req.active_goal,
            failed_approaches=[
                FailedApproachRecord(
                    approach_name=fa.approach_name,
                    rejected_reason=fa.rejected_reason,
                    evidence_snippet=fa.evidence_snippet,
                    attempted_by_profile_id=fa.attempted_by_profile_id,
                )
                for fa in req.failed_approaches
            ],
            implicit_constraints=[
                ImplicitConstraintRecord(
                    scope=ic.scope,
                    constraint_rule=ic.constraint_rule,
                    rationale=ic.rationale,
                )
                for ic in req.implicit_constraints
            ],
            errors_and_fixes=list(req.errors_and_fixes),
            pending_asks=list(req.pending_asks),
            next_actions=list(req.next_actions),
        )
        result: FinalizeSessionResult = self._engine.finalize_session(harness_req)
        return FinalizeSessionResponseDTO(
            session_id=result.session_id,
            handoff_id=result.handoff_id,
            persisted_path=result.persisted_path,
            status=result.status.value,
            timestamp=result.timestamp,
        )

    def claim_handoff(self, handoff_id: str, req: ClaimHandoffRequestDTO) -> HandoffClaimReceiptDTO:
        """Atomically claim a pending handoff, enforcing mutual exclusion."""
        receipt: HandoffClaimReceipt = self._engine.claim_handoff(
            handoff_id=handoff_id,
            claimer_profile_id=req.claimer_profile_id,
            claimer_session_id=req.claimer_session_id,
        )
        return HandoffClaimReceiptDTO(
            handoff_id=receipt.handoff_id,
            claimed_by_profile_id=receipt.claimed_by_profile_id,
            claimed_by_session_id=receipt.claimed_by_session_id,
            claim_timestamp=receipt.claim_timestamp,
            handoff_spec=_spec_to_dto(receipt.handoff_spec),
        )

    def complete_handoff(self, handoff_id: str, req: CompleteHandoffRequestDTO) -> AgentHandoffSpecDTO:
        """Mark a claimed handoff memorandum as completed."""
        updated = self._engine.complete_handoff(
            handoff_id=handoff_id,
            completing_session_id=req.completing_session_id,
        )
        return _spec_to_dto(updated)

    def cancel_handoff(self, handoff_id: str, req: CancelHandoffRequestDTO) -> AgentHandoffSpecDTO:
        """Cancel an existing pending or claimed handoff packet."""
        cancelled = self._engine.cancel_handoff(
            handoff_id=handoff_id,
            cancelling_session_id=req.cancelling_session_id,
            reason=req.reason,
        )
        return _spec_to_dto(cancelled)

    def get_handoff(self, handoff_id: str) -> AgentHandoffSpecDTO | None:
        """Retrieve a specific handoff memorandum by ID."""
        spec = self._engine.get_handoff(handoff_id)
        if spec is None:
            return None
        return _spec_to_dto(spec)

    def list_pending(self, target_profile_id: str | None = None) -> HandoffListResponseDTO:
        """List all unassigned or matching pending handoff memorandums."""
        specs = self._engine.list_pending(target_profile_id=target_profile_id)
        dtos = [_spec_to_dto(s) for s in specs]
        return HandoffListResponseDTO(handoffs=dtos, total_count=len(dtos))

    def list_by_session(self, session_id: str) -> HandoffListResponseDTO:
        """List all handoff records associated with a specific session ID."""
        specs = self._engine.list_by_session(session_id=session_id)
        dtos = [_spec_to_dto(s) for s in specs]
        return HandoffListResponseDTO(handoffs=dtos, total_count=len(dtos))


_AGENT_HANDOFF_SERVICE_INSTANCE: AgentHandoffService | None = None
_AGENT_HANDOFF_SERVICE_LOCK = threading.Lock()


def get_agent_handoff_service() -> AgentHandoffService:
    """Singleton provider for AgentHandoffService."""
    global _AGENT_HANDOFF_SERVICE_INSTANCE
    if _AGENT_HANDOFF_SERVICE_INSTANCE is None:
        with _AGENT_HANDOFF_SERVICE_LOCK:
            if _AGENT_HANDOFF_SERVICE_INSTANCE is None:
                _AGENT_HANDOFF_SERVICE_INSTANCE = AgentHandoffService()
    return _AGENT_HANDOFF_SERVICE_INSTANCE
