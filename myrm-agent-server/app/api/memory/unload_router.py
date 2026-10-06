"""
[POS] app/api/memory/unload_router.py
[INPUT] fastapi, app/schemas/memory_unload.py, app/services/memory/memory_unload_service.py
[OUTPUT] router

FastAPI router exposing desktop and WebUI graceful flush and unload finalize endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_unload import (
    AcknowledgeSessionRequestDTO,
    AcknowledgeSessionResponseDTO,
    EmergencyFlushRequestDTO,
    EmergencyFlushResponseDTO,
    ListUnfinalizedResponseDTO,
)
from app.services.memory.memory_unload_service import (
    MemoryUnloadService,
    get_memory_unload_service,
)

router = APIRouter()


@router.post(
    "/unload/flush",
    response_model=EmergencyFlushResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute zero-LLM crash-proof emergency memory flush on unload",
)
def emergency_flush(
    request: EmergencyFlushRequestDTO,
    service: MemoryUnloadService = Depends(get_memory_unload_service),
) -> EmergencyFlushResponseDTO:
    """Flush pending unsaved notes and context snapshot to durable memorandum upon page unload."""
    return service.emergency_flush(request)


@router.get(
    "/unload/unfinalized",
    response_model=ListUnfinalizedResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List unfinalized sessions awaiting startup restoration or review",
)
def list_unfinalized_sessions(
    service: MemoryUnloadService = Depends(get_memory_unload_service),
) -> ListUnfinalizedResponseDTO:
    """Retrieve list of unfinalized sessions preserved from previous desktop or browser exits."""
    return service.list_unfinalized()


@router.post(
    "/unload/acknowledge",
    response_model=AcknowledgeSessionResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge and mark an unfinalized session as claimed or dismissed",
)
def acknowledge_unfinalized_session(
    request: AcknowledgeSessionRequestDTO,
    service: MemoryUnloadService = Depends(get_memory_unload_service),
) -> AcknowledgeSessionResponseDTO:
    """Mark an unfinalized session handoff as claimed, dismissing startup recovery alerts."""
    return service.acknowledge_session(request)
