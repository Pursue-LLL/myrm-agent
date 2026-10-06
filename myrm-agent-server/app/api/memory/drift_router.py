"""
[POS] app/api/memory/drift_router.py
[INPUT] fastapi, app/schemas/memory_drift.py, app/services/memory/memory_drift_service.py
[OUTPUT] router

FastAPI router exposing ground truth memory drift checking and stale defense endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_drift import (
    BatchDriftCheckRequestDTO,
    BatchDriftCheckResponseDTO,
    DriftCheckRequestDTO,
    DriftCheckResponseDTO,
)
from app.services.memory.memory_drift_service import (
    MemoryDriftService,
    get_memory_drift_service,
)

router = APIRouter()


@router.post(
    "/drift/check",
    response_model=DriftCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate an individual memory for code and configuration drift",
)
def check_memory_drift(
    request: DriftCheckRequestDTO,
    service: MemoryDriftService = Depends(get_memory_drift_service),
) -> DriftCheckResponseDTO:
    """Inspect memory statement against physical repository state and inject warning if stale."""
    return service.check(request)


@router.post(
    "/drift/check-batch",
    response_model=BatchDriftCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Batch evaluate candidate memories before prompt injection",
)
def check_batch_memory_drift(
    request: BatchDriftCheckRequestDTO,
    service: MemoryDriftService = Depends(get_memory_drift_service),
) -> BatchDriftCheckResponseDTO:
    """Batch inspect candidate memories, flagging obsolete files/symbols and calculating penalties."""
    return service.check_batch(request)
