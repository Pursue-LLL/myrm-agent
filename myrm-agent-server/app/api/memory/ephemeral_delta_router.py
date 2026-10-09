# [POS]: app/api/memory/ephemeral_delta_router.py
# [INPUT]: app.schemas.ephemeral_delta, app.services.memory.ephemeral_delta_service
# [OUTPUT]: router (FastAPI APIRouter for ephemeral delta memory operations)

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.schemas.ephemeral_delta import (
    EphemeralDeltaBufferSnapshotDTO,
    EphemeralDeltaItemDTO,
    ReconcileSessionResponse,
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
    "/reconcile/{session_id}",
    response_model=ReconcileSessionResponse,
    summary="Reconcile session deltas into durable storage",
)
async def reconcile_session(
    session_id: Annotated[str, Path(description="Target session identifier")],
    service: Annotated[EphemeralDeltaService, Depends(get_ephemeral_delta_service)],
) -> ReconcileSessionResponse:
    """Flush and collapse transient session deltas into permanent storage."""
    return await service.reconcile_session(session_id)
