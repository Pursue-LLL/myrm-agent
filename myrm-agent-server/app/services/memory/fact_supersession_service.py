"""FactSupersessionService, get_fact_supersession_service.

[POS]
app/services/memory/fact_supersession_service.py

[INPUT]
- app.schemas.fact_supersession, myrm_agent_harness.toolkits.memory

[OUTPUT]
- FactSupersessionService, get_fact_supersession_service
"""

from __future__ import annotations

import logging
import uuid

from myrm_agent_harness.toolkits.memory import (
    ContradictionQuarantineGate,
    ContradictionQuarantineItem,
    DialecticRecallProjection,
    DialecticRecallProjector,
    FactSupersessionChainEngine,
    TemporalFactRecord,
    TemporalFactStatus,
)

from app.schemas.fact_supersession import (
    DialecticRecallResponseDTO,
    FactHistoryResponseDTO,
    QuarantineItemDTO,
    RegisterFactRequest,
    RegisterFactResponse,
    ResolveQuarantineRequest,
    TemporalFactRecordDTO,
    TimeTravelRecallRequest,
)

logger = logging.getLogger(__name__)


def _to_fact_dto(record: TemporalFactRecord) -> TemporalFactRecordDTO:
    return TemporalFactRecordDTO(
        fact_id=record.fact_id,
        subject=record.subject,
        predicate=record.predicate,
        object_value=record.object_value,
        valid_from=record.valid_from,
        valid_until=record.valid_until,
        superseded_by=record.superseded_by,
        confidence=record.confidence,
        status=record.status.value,
        source_session_id=record.source_session_id,
        evidence_quote=record.evidence_quote,
        created_at=record.created_at,
    )


def _to_quarantine_dto(item: ContradictionQuarantineItem) -> QuarantineItemDTO:
    return QuarantineItemDTO(
        quarantine_id=item.quarantine_id,
        new_fact=_to_fact_dto(item.new_fact),
        conflicting_fact_id=item.conflicting_fact_id,
        conflict_score=item.conflict_score,
        detected_at=item.detected_at,
        status=item.status,
    )


class FactSupersessionService:
    """Application service coordinating temporal fact validity, supersession chains, and contradiction gates."""

    def __init__(
        self,
        chain_engine: FactSupersessionChainEngine | None = None,
        quarantine_gate: ContradictionQuarantineGate | None = None,
        projector: DialecticRecallProjector | None = None,
    ) -> None:
        self._chain_engine = chain_engine or FactSupersessionChainEngine()
        self._quarantine_gate = quarantine_gate or ContradictionQuarantineGate()
        self._projector = projector or DialecticRecallProjector()

    def register_fact(self, req: RegisterFactRequest) -> RegisterFactResponse:
        """Register a fact assertion, passing through the contradiction evaluation gate."""
        fact_id = f"fact-{uuid.uuid4().hex[:8]}"
        domain_fact = TemporalFactRecord(
            fact_id=fact_id,
            subject=req.subject,
            predicate=req.predicate,
            object_value=req.object_value,
            valid_from=req.valid_from,
            confidence=req.confidence,
            status=TemporalFactStatus.ACTIVE,
            source_session_id=req.source_session_id,
            evidence_quote=req.evidence_quote,
        )

        action_taken, result = self._quarantine_gate.ingest_fact(
            new_fact=domain_fact,
            chain_engine=self._chain_engine,
        )

        if action_taken == "QUARANTINED" and isinstance(result, ContradictionQuarantineItem):
            return RegisterFactResponse(
                action_taken="QUARANTINED",
                fact=_to_fact_dto(result.new_fact),
                quarantine_id=result.quarantine_id,
            )
        elif isinstance(result, TemporalFactRecord):
            return RegisterFactResponse(
                action_taken=action_taken,
                fact=_to_fact_dto(result),
            )
        else:
            return RegisterFactResponse(
                action_taken=action_taken,
                fact=_to_fact_dto(domain_fact),
            )

    def recall(self, req: TimeTravelRecallRequest) -> DialecticRecallResponseDTO:
        """Execute explainable recall with ancestral lineage and optional point-in-time time-travel."""
        projection: DialecticRecallProjection = self._projector.project_recall(
            chain_engine=self._chain_engine,
            subject=req.subject,
            predicate=req.predicate,
            as_of_time=req.as_of_time,
        )

        lineage_dtos: dict[str, list[TemporalFactRecordDTO]] = {
            f_id: [_to_fact_dto(anc) for anc in ancestors]
            for f_id, ancestors in projection.superseded_lineage.items()
        }

        return DialecticRecallResponseDTO(
            active_facts=[_to_fact_dto(f) for f in projection.active_facts],
            superseded_lineage=lineage_dtos,
            as_of_time=projection.as_of_time,
            total_matched=projection.total_matched,
        )

    def list_quarantine(self, status: str | None = "quarantined") -> list[QuarantineItemDTO]:
        """List contradiction items held in the quarantine ledger."""
        items = self._quarantine_gate.list_quarantined(status=status)
        return [_to_quarantine_dto(i) for i in items]

    def resolve_quarantine(
        self,
        quarantine_id: str,
        req: ResolveQuarantineRequest,
    ) -> RegisterFactResponse:
        """Human resolution action: approve override to supersede, or reject candidate."""
        approved, active_fact = self._quarantine_gate.resolve_quarantine(
            quarantine_id=quarantine_id,
            approve_override=req.approve_override,
            chain_engine=self._chain_engine,
        )

        if approved and active_fact:
            return RegisterFactResponse(
                action_taken="SUPERSEDED",
                fact=_to_fact_dto(active_fact),
            )
        else:
            return RegisterFactResponse(
                action_taken="REJECTED",
                fact=None,
            )

    def get_fact_history(self, fact_id: str) -> FactHistoryResponseDTO:
        """Trace historical ancestor facts superseded leading to the target fact."""
        ancestors = self._chain_engine.get_supersession_history(fact_id)
        return FactHistoryResponseDTO(
            fact_id=fact_id,
            ancestor_facts=[_to_fact_dto(a) for a in ancestors],
        )


_instance: FactSupersessionService | None = None


def get_fact_supersession_service() -> FactSupersessionService:
    """Dependency provider for singleton FactSupersessionService."""
    global _instance
    if _instance is None:
        _instance = FactSupersessionService()
    return _instance
