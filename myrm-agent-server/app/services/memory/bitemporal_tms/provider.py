"""Service provider for bitemporal truth maintenance.

[POS]
Adapter layer bridging FastAPI routers to the underlying harness bitemporal TMS engine.
Converts domain entities to strictly typed Pydantic V2 DTOs.

[INPUT]
- app.schemas.bitemporal_tms
- myrm_agent_harness.toolkits.memory.bitemporal_truth_maintenance.facade
- myrm_agent_harness.toolkits.memory.bitemporal_truth_maintenance.models

[OUTPUT]
- BitemporalTmsProvider
- get_bitemporal_tms_provider
"""

from __future__ import annotations

import time

from myrm_agent_harness.toolkits.memory.bitemporal_truth_maintenance.facade import (
    BitemporalTruthMaintenanceFacade,
    get_bitemporal_truth_maintenance_facade,
)
from myrm_agent_harness.toolkits.memory.bitemporal_truth_maintenance.models import (
    BitemporalEvidenceRecord,
    EvidenceType,
    TemporalQueryCriteria,
)

from app.schemas.bitemporal_tms import (
    BitemporalCoordinatesDTO,
    DeriveInferenceRequest,
    EvidenceRecordDTO,
    RecordFactRequest,
    RetractRecordRequest,
    RetractRecordResponse,
    SnapshotRequest,
    SnapshotResponse,
    TemporalQueryRequest,
    TemporalQueryResponse,
    TimeIntervalDTO,
)


class BitemporalTmsProvider:
    """Orchestrates bitemporal truth maintenance operations for application endpoints."""

    def __init__(
        self,
        facade: BitemporalTruthMaintenanceFacade | None = None,
    ) -> None:
        self._facade = facade or get_bitemporal_truth_maintenance_facade()

    def record_fact(self, request: RecordFactRequest) -> EvidenceRecordDTO:
        """Records an external ground truth fact."""
        record = self._facade.record_fact(
            evidence_id=request.evidence_id,
            content=request.content,
            valid_start=request.valid_start,
            valid_end=request.valid_end,
            known_start=request.known_start,
            confidence=request.confidence,
            metadata=request.metadata,
        )
        return self._to_dto(record)

    def derive_inference(self, request: DeriveInferenceRequest) -> EvidenceRecordDTO:
        """Derives a reasoned inference supported by premise justifications."""
        record = self._facade.derive_inference(
            inference_id=request.inference_id,
            content=request.content,
            premise_ids=request.premise_ids,
            justification=request.justification,
            valid_start=request.valid_start,
            valid_end=request.valid_end,
            known_start=request.known_start,
            causal_distance=request.causal_distance,
            confidence=request.confidence,
            metadata=request.metadata,
        )
        return self._to_dto(record)

    def retract_record(self, request: RetractRecordRequest) -> RetractRecordResponse:
        """Non-destructively marks an evidence record as retracted."""
        now = time.time()
        r_time = now if request.retracted_at is None else request.retracted_at
        success = self._facade.retract_record(
            evidence_id=request.evidence_id,
            retracted_at=r_time,
        )
        return RetractRecordResponse(
            success=success,
            evidence_id=request.evidence_id,
            retracted_at=r_time,
        )

    def query_active(self, request: TemporalQueryRequest) -> TemporalQueryResponse:
        """Queries active memory records matching criteria and active justification support."""
        now = time.time()
        v_time = now if request.as_of_valid_time is None else request.as_of_valid_time
        k_time = now if request.as_of_known_time is None else request.as_of_known_time

        parsed_types: tuple[EvidenceType, ...] | None = None
        if request.evidence_types:
            type_list: list[EvidenceType] = []
            for t_str in request.evidence_types:
                try:
                    type_list.append(EvidenceType(t_str.strip().lower()))
                except ValueError:
                    continue
            if type_list:
                parsed_types = tuple(type_list)

        criteria = TemporalQueryCriteria(
            as_of_valid_time=v_time,
            as_of_known_time=k_time,
            require_active_support=request.require_active_support,
            min_confidence=request.min_confidence,
            evidence_types=parsed_types,
        )

        records = self._facade.query_active(criteria)
        dtos = [self._to_dto(r) for r in records]

        return TemporalQueryResponse(
            total=len(dtos),
            records=dtos,
            as_of_valid_time=v_time,
            as_of_known_time=k_time,
        )

    def project_snapshot(self, request: SnapshotRequest) -> SnapshotResponse:
        """Projects a bitemporal truth maintenance snapshot separating active vs invalidated entities."""
        now = time.time()
        v_time = now if request.as_of_valid_time is None else request.as_of_valid_time
        k_time = now if request.as_of_known_time is None else request.as_of_known_time

        snap = self._facade.project_snapshot(
            as_of_valid_time=v_time,
            as_of_known_time=k_time,
        )

        return SnapshotResponse(
            active_evidences=[self._to_dto(r) for r in snap.active_evidences],
            retracted_evidences=[self._to_dto(r) for r in snap.retracted_evidences],
            active_inferences=[self._to_dto(r) for r in snap.active_inferences],
            invalidated_inferences=[self._to_dto(r) for r in snap.invalidated_inferences],
            as_of_valid_time=snap.as_of_valid_time,
            as_of_known_time=snap.as_of_known_time,
            total_count=snap.total_count,
        )

    @staticmethod
    def _to_dto(record: BitemporalEvidenceRecord) -> EvidenceRecordDTO:
        """Converts an internal domain record to an external DTO."""
        valid_dto = TimeIntervalDTO(
            start=record.bitemporal.valid_interval.start,
            end=record.bitemporal.valid_interval.end,
        )
        known_dto = TimeIntervalDTO(
            start=record.bitemporal.known_interval.start,
            end=record.bitemporal.known_interval.end,
        )
        coords_dto = BitemporalCoordinatesDTO(
            valid_interval=valid_dto,
            known_interval=known_dto,
        )
        return EvidenceRecordDTO(
            evidence_id=record.evidence_id,
            content=record.content,
            evidence_type=record.evidence_type.value,
            bitemporal=coords_dto,
            confidence=record.confidence,
            metadata=dict(record.metadata),
        )


_GLOBAL_PROVIDER: BitemporalTmsProvider | None = None


def get_bitemporal_tms_provider() -> BitemporalTmsProvider:
    """FastAPI dependency injection factory for BitemporalTmsProvider."""
    global _GLOBAL_PROVIDER
    if _GLOBAL_PROVIDER is None:
        _GLOBAL_PROVIDER = BitemporalTmsProvider()
    return _GLOBAL_PROVIDER
