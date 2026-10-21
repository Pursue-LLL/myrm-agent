"""router (FastAPI APIRouter for ephemeral delta memory operations).

[POS]
app/api/memory/ephemeral_delta_router.py

[INPUT]
- app.schemas.ephemeral_delta, app.services.memory.ephemeral_delta_service

[OUTPUT]
- router (FastAPI APIRouter for ephemeral delta memory operations)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.schemas.ephemeral_delta import (
    EphemeralDeltaBufferSnapshotDTO,
    EphemeralDeltaItemDTO,
    PreviewDeltaInjectionRequestDTO,
    PreviewDeltaInjectionResponseDTO,
    PromptCacheMetricsDTO,
    RecordEphemeralDeltaRequest,
)
from app.services.memory.ephemeral_delta_service import (
    EphemeralDeltaService,
    get_ephemeral_delta_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ephemeral-delta", tags=["Ephemeral Delta Memory"])


@router.post(
    "/record",
    response_model=EphemeralDeltaItemDTO,
    summary="Record an ephemeral session delta",
)
async def record_delta(
    request: RecordEphemeralDeltaRequest,
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> EphemeralDeltaItemDTO:
    """Record an ephemeral user correction or inferred fact without invalidating prompt cache."""
    return service.record_delta(request)


@router.get(
    "/active/{session_id}",
    response_model=list[EphemeralDeltaItemDTO],
    summary="Get active ephemeral deltas for session",
)
async def get_active_deltas(
    session_id: Annotated[str, Path(description="Target session identifier")],
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> list[EphemeralDeltaItemDTO]:
    """Retrieve active non-retracted deltas after LWW deduplication for the session."""
    return service.get_active_deltas(session_id)


@router.get(
    "/snapshot/{session_id}",
    response_model=EphemeralDeltaBufferSnapshotDTO,
    summary="Get session ephemeral delta buffer snapshot",
)
async def get_snapshot(
    session_id: Annotated[str, Path(description="Target session identifier")],
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> EphemeralDeltaBufferSnapshotDTO:
    """Get snapshot of current session ephemeral buffer state."""
    return service.get_snapshot(session_id)


@router.post(
    "/preview",
    response_model=PreviewDeltaInjectionResponseDTO,
    summary="Preview prompt cache preserving delta injection",
)
async def preview_delta_injection(
    request: PreviewDeltaInjectionRequestDTO,
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> PreviewDeltaInjectionResponseDTO:
    """Simulate frozen prefix preservation and HumanMessage tail XML delta injection."""
    return service.preview_injection(request)


@router.get(
    "/metrics/{session_id}",
    response_model=PromptCacheMetricsDTO,
    summary="Get prompt cache telemetry metrics for session",
)
async def get_cache_metrics(
    session_id: Annotated[str, Path(description="Target session identifier")],
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> PromptCacheMetricsDTO:
    """Layout diagnostics only (delta count; no provider cache hit ratio)."""
    return service.get_metrics(session_id)
