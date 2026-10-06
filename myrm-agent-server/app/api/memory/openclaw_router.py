"""
[POS] app/api/memory/openclaw_router.py
[INPUT] fastapi, app/schemas/memory_openclaw.py, app/services/memory/memory_openclaw_service.py
[OUTPUT] router

FastAPI router exposing OpenClaw 2.0 format translation, Swarm session trees, and SQLite crash recovery endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_openclaw import (
    OpenClawImportV2RequestDTO,
    OpenClawImportV2ResponseDTO,
    OpenClawRescuePreviewRequestDTO,
    OpenClawRescuePreviewResponseDTO,
)
from app.services.memory.memory_openclaw_service import (
    MemoryOpenClawService,
    get_memory_openclaw_service,
)

router = APIRouter()


@router.post(
    "/openclaw/rescue-preview",
    response_model=OpenClawRescuePreviewResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Probe OpenClaw SQLite database integrity and preview salvageable records",
)
def rescue_preview(
    request: OpenClawRescuePreviewRequestDTO,
    service: MemoryOpenClawService = Depends(get_memory_openclaw_service),
) -> OpenClawRescuePreviewResponseDTO:
    """Diagnose database corruption, execute read-only fault-tolerant extraction, and preview sessions/memories."""
    return service.rescue_preview(request)


@router.post(
    "/openclaw/import-v2",
    response_model=OpenClawImportV2ResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Import OpenClaw 2.0 multi-user, Swarm topology, and structured memories into Myrm",
)
def import_v2_bundle(
    request: OpenClawImportV2RequestDTO,
    service: MemoryOpenClawService = Depends(get_memory_openclaw_service),
) -> OpenClawImportV2ResponseDTO:
    """Ingest sessions (preserving Swarm lineage) and memories with private/shared scope alignment."""
    return service.import_v2_bundle(request)
