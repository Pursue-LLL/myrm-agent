"""
[POS] app/services/memory/memory_conflict_service.py
[INPUT] threading.Lock, uuid.uuid4, myrm_agent_harness.toolkits.memory.conflict_arbitration, app/schemas/memory_conflict.py
[OUTPUT] MemoryConflictService, get_memory_conflict_service

Business service mediating memory conflict evaluation, pending arbitration staging, and user-confirmed decision freeze locking.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
import uuid
from threading import Lock

from myrm_agent_harness.toolkits.memory.conflict_arbitration import (
    ArbitrationAssessment,
    ConflictResolutionKind,
    HumanArbitrationDecision,
    MemorySemanticArbitrator,
    SemanticConflictRecord,
    UserConfirmedFreezeGate,
    UserConfirmedFreezeLock,
)

from app.schemas.memory_conflict import (
    EvaluateConflictRequestDTO,
    EvaluateConflictResponseDTO,
    FreezeLockStatusResponseDTO,
    HumanArbitrateRequestDTO,
    HumanArbitrateResponseDTO,
    PendingConflictItemDTO,
    PendingConflictListResponseDTO,
    UnlockDecisionRequestDTO,
    UnlockDecisionResponseDTO,
)

logger = logging.getLogger(__name__)


class MemoryConflictService:
    """Service managing conflict arbitration workflows and immutable freeze locks."""

    def __init__(
        self,
        arbitrator: MemorySemanticArbitrator | None = None,
        freeze_gate: UserConfirmedFreezeGate | None = None,
    ) -> None:
        self._lock: Lock = Lock()
        self._arbitrator: MemorySemanticArbitrator = arbitrator or MemorySemanticArbitrator()
        self._freeze_gate: UserConfirmedFreezeGate = freeze_gate or UserConfirmedFreezeGate()
        self._pending_conflicts: dict[str, SemanticConflictRecord] = {}

    @property
    def freeze_gate(self) -> UserConfirmedFreezeGate:
        """Access the underlying freeze gate instance."""
        return self._freeze_gate

    @property
    def arbitrator(self) -> MemorySemanticArbitrator:
        """Access the underlying semantic arbitrator instance."""
        return self._arbitrator

    def evaluate_and_stage(self, request: EvaluateConflictRequestDTO) -> EvaluateConflictResponseDTO:
        """Evaluate conflict between existing memory and incoming candidate fact."""
        with self._lock:
            conflict_id = f"conf-{uuid.uuid4().hex[:12]}"
            is_frozen = self._freeze_gate.is_frozen(request.existing_memory_id)

            record = self._arbitrator.detect_conflict_between_facts(
                conflict_id=conflict_id,
                entity_key=request.entity_key,
                attribute_name=request.attribute_name,
                existing_memory_id=request.existing_memory_id,
                existing_fact_text=request.existing_fact_text,
                candidate_fact_text=request.candidate_fact_text,
                is_existing_frozen=is_frozen,
                source_context=request.source_context,
            )

            assessment: ArbitrationAssessment = self._arbitrator.evaluate_conflict(record)

            is_staged = False
            if assessment.requires_human_confirmation and request.auto_stage_if_disputed:
                self._pending_conflicts[conflict_id] = record
                is_staged = True
                logger.info(
                    "Staged conflict '%s' for human arbitration card review (entity='%s').",
                    conflict_id,
                    request.entity_key,
                )

            return EvaluateConflictResponseDTO(
                conflict_id=conflict_id,
                resolution_kind=assessment.resolution_kind.value,
                confidence=assessment.confidence,
                reasoning=assessment.reasoning,
                suggested_text=assessment.suggested_text,
                requires_human_confirmation=assessment.requires_human_confirmation,
                is_staged_in_pending=is_staged,
            )

    def list_pending_conflicts(self) -> PendingConflictListResponseDTO:
        """List all conflicts currently awaiting human arbitration."""
        with self._lock:
            items: list[PendingConflictItemDTO] = []
            for cid, rec in self._pending_conflicts.items():
                items.append(
                    PendingConflictItemDTO(
                        conflict_id=cid,
                        entity_key=rec.entity_key,
                        attribute_name=rec.attribute_name,
                        existing_memory_id=rec.existing_memory_id,
                        existing_fact_text=rec.existing_fact_text,
                        candidate_fact_text=rec.candidate_fact_text,
                        severity=rec.severity.value,
                        detected_at=rec.detected_at.isoformat(),
                        source_context=rec.source_context,
                        is_existing_frozen=rec.is_existing_frozen,
                    )
                )
            return PendingConflictListResponseDTO(
                total_count=len(items),
                items=items,
            )

    def apply_human_arbitration(self, request: HumanArbitrateRequestDTO) -> HumanArbitrateResponseDTO:
        """Apply a human operator's final judgment and optionally freeze-lock the decision."""
        with self._lock:
            pending_rec = self._pending_conflicts.pop(request.conflict_id, None)
            target_memory_id = pending_rec.existing_memory_id if pending_rec is not None else request.conflict_id

            try:
                resolution_enum = ConflictResolutionKind(request.chosen_resolution)
            except ValueError:
                resolution_enum = ConflictResolutionKind.OVERRIDE

            decision = HumanArbitrationDecision(
                conflict_id=request.conflict_id,
                chosen_resolution=resolution_enum,
                final_fact_text=request.final_fact_text,
                operator_id=request.operator_id,
                should_freeze_lock=request.should_freeze_lock,
                comment=request.comment,
            )

            immutable_hash: str | None = None
            is_frozen = False
            if decision.should_freeze_lock:
                lock: UserConfirmedFreezeLock = self._freeze_gate.freeze(
                    memory_id=target_memory_id,
                    content=decision.final_fact_text,
                    confirmed_by=decision.operator_id,
                )
                immutable_hash = lock.immutable_hash
                is_frozen = True

            logger.info(
                "Human arbitration applied for conflict '%s'. Frozen: %s, Hash: %s",
                request.conflict_id,
                is_frozen,
                immutable_hash,
            )

            return HumanArbitrateResponseDTO(
                success=True,
                conflict_id=request.conflict_id,
                final_fact_text=decision.final_fact_text,
                is_frozen=is_frozen,
                immutable_hash=immutable_hash,
                message=f"Conflict '{request.conflict_id}' finalized by '{request.operator_id}'.",
            )

    def get_freeze_status(self, memory_id: str) -> FreezeLockStatusResponseDTO:
        """Query the freeze lock status and integrity of a specific memory record."""
        with self._lock:
            lock = self._freeze_gate.get_lock(memory_id)
            if lock is None or not lock.is_active:
                return FreezeLockStatusResponseDTO(
                    memory_id=memory_id,
                    is_frozen=False,
                    frozen_content=None,
                    confirmed_by=None,
                    confirmed_at=None,
                    immutable_hash=None,
                    lock_version=1,
                    integrity_valid=True,
                )

            return FreezeLockStatusResponseDTO(
                memory_id=memory_id,
                is_frozen=True,
                frozen_content=lock.frozen_content,
                confirmed_by=lock.confirmed_by,
                confirmed_at=lock.confirmed_at.isoformat(),
                immutable_hash=lock.immutable_hash,
                lock_version=lock.lock_version,
                integrity_valid=lock.verify_integrity(),
            )

    def unlock_decision(self, request: UnlockDecisionRequestDTO) -> UnlockDecisionResponseDTO:
        """Explicitly unlock a user-confirmed frozen decision."""
        with self._lock:
            success = self._freeze_gate.unlock(
                memory_id=request.memory_id,
                operator_id=request.operator_id,
                reason=request.reason,
            )
            msg = (
                f"Memory '{request.memory_id}' unlocked by '{request.operator_id}'."
                if success
                else f"Memory '{request.memory_id}' was not actively locked."
            )
            return UnlockDecisionResponseDTO(
                success=success,
                memory_id=request.memory_id,
                message=msg,
            )


_conflict_service_instance: MemoryConflictService | None = None
_conflict_service_lock: Lock = Lock()


def get_memory_conflict_service() -> MemoryConflictService:
    """Singleton provider for MemoryConflictService."""
    global _conflict_service_instance
    with _conflict_service_lock:
        if _conflict_service_instance is None:
            _conflict_service_instance = MemoryConflictService()
        return _conflict_service_instance
