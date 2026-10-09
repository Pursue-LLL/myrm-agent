"""FastAPI router for bitemporal truth maintenance and justification reasoning.

[POS]
HTTP boundary for bitemporal coordinate tracking, non-destructive evidence retraction,
justification graph reasoning, and time-travel query projection.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.bitemporal_tms
- app.services.memory.bitemporal_tms

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.bitemporal_tms import (
    BitemporalTmsHealthResponse,
    DeriveInferenceRequest,
    EvidenceRecordDTO,
    RecordFactRequest,
    RetractRecordRequest,
    RetractRecordResponse,
    SnapshotRequest,
    SnapshotResponse,
    TemporalQueryRequest,
    TemporalQueryResponse,
)
from app.services.memory.bitemporal_tms import (
    BitemporalTmsProvider,
    get_bitemporal_tms_provider,
)

router = APIRouter(prefix="/bitemporal-tms", tags=["Bitemporal Truth Maintenance"])


@router.post(
    "/facts",
    response_model=EvidenceRecordDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record external ground fact with bitemporal validity and assertion timestamps",
)
async def record_fact(
    request: RecordFactRequest,
    provider: Annotated[
        BitemporalTmsProvider,
        Depends(get_bitemporal_tms_provider),
    ],
) -> EvidenceRecordDTO:
    """Records an external ground truth fact with mathematically validated half-open intervals."""
    return provider.record_fact(request)


@router.post(
    "/inferences",
    response_model=EvidenceRecordDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Derive reasoned inference supported by premise justification links",
)
async def derive_inference(
    request: DeriveInferenceRequest,
    provider: Annotated[
        BitemporalTmsProvider,
        Depends(get_bitemporal_tms_provider),
    ],
) -> EvidenceRecordDTO:
    """Derives a reasoned inference with premise dependencies and topological causal distance."""
    return provider.derive_inference(request)


@router.post(
    "/retract",
    response_model=RetractRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Non-destructively retract an evidence record while preserving historical state",
)
async def retract_record(
    request: RetractRecordRequest,
    provider: Annotated[
        BitemporalTmsProvider,
        Depends(get_bitemporal_tms_provider),
    ],
) -> RetractRecordResponse:
    """Closes known_interval of evidence record, invalidating active temporal support."""
    return provider.retract_record(request)


@router.post(
    "/query",
    response_model=TemporalQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query active memory records at target bitemporal coordinates",
)
async def query_active(
    request: TemporalQueryRequest,
    provider: Annotated[
        BitemporalTmsProvider,
        Depends(get_bitemporal_tms_provider),
    ],
) -> TemporalQueryResponse:
    """Executes time-travel queries strictly filtering by active justifications."""
    return provider.query_active(request)


@router.post(
    "/snapshot",
    response_model=SnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="Project bitemporal snapshot separating active vs invalidated memory entities",
)
async def project_snapshot(
    request: SnapshotRequest,
    provider: Annotated[
        BitemporalTmsProvider,
        Depends(get_bitemporal_tms_provider),
    ],
) -> SnapshotResponse:
    """Projects comprehensive truth maintenance state across primitive facts and derived inferences."""
    return provider.project_snapshot(request)


@router.get(
    "/health",
    response_model=BitemporalTmsHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check probe for bitemporal truth maintenance subsystem",
)
async def bitemporal_tms_health() -> BitemporalTmsHealthResponse:
    """Returns operational health status of bitemporal TMS subsystem."""
    return BitemporalTmsHealthResponse()
