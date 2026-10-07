"""
[POS] app/api/memory/subagent_isolation.py
[INPUT] fastapi, app.schemas.memory_subagent_isolation, app.services.memory.memory_subagent_isolation_service
[OUTPUT] router

FastAPI router exposing endpoints for Adaptive Subagent Memory Isolation and Context Compression Flush Protocol.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.memory_subagent_isolation import (
    AppendSubagentEphemeralRequestDTO,
    CreateSubagentOverlayRequestDTO,
    ExecutePreCompressionFlushRequestDTO,
    FlushItemDTO,
    FlushResultDTO,
    MergeSelectiveRequestDTO,
    RegisterPendingFlushRequestDTO,
    StatelessCronSanitizeRequestDTO,
    StatelessCronSanitizeResponseDTO,
)
from app.services.memory.memory_subagent_isolation_service import (
    MemorySubagentIsolationService,
    get_memory_subagent_isolation_service,
)

router = APIRouter()


class PendingCountResponseDTO(BaseModel):
    """Response returning pending flush items count for a session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session ID")
    pending_count: int = Field(..., ge=0, description="Count of pending items awaiting flush")


class SubagentOverlayStatusResponseDTO(BaseModel):
    """Response returning creation or operation status for subagent overlay."""

    model_config = ConfigDict(extra="forbid")

    overlay_id: str = Field(..., description="Target overlay ID")
    is_success: bool = Field(..., description="True if operation succeeded")


@router.post(
    "/isolation/flush/pending",
    response_model=PendingCountResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Register transient items pending pre-compression flush",
)
def register_pending_flush_items(
    payload: RegisterPendingFlushRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> PendingCountResponseDTO:
    """Buffer ephemeral items into pending queue awaiting context compression flush."""
    count = service.register_pending_items(payload.session_id, payload.items)
    return PendingCountResponseDTO(session_id=payload.session_id, pending_count=count)


@router.post(
    "/isolation/flush/execute",
    response_model=FlushResultDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute pre-compression memory flush gate before summarizing or pruning context",
)
def execute_pre_compression_flush(
    payload: ExecutePreCompressionFlushRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> FlushResultDTO:
    """Flush pending ephemeral items to storage before context compression to eliminate memory loss."""
    return service.execute_pre_compression_flush(payload.session_id, payload.reason)


@router.post(
    "/isolation/subagent/overlay",
    response_model=SubagentOverlayStatusResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Instantiate an isolated ephemeral memory overlay sandbox for a subagent",
)
def create_subagent_memory_overlay(
    payload: CreateSubagentOverlayRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> SubagentOverlayStatusResponseDTO:
    """Create isolated sandbox mounting parent read-only snapshot and private scratch overlay."""
    is_created = service.create_subagent_overlay(payload)
    return SubagentOverlayStatusResponseDTO(overlay_id=payload.spec.overlay_id, is_success=is_created)


@router.post(
    "/isolation/subagent/append",
    response_model=SubagentOverlayStatusResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Append a transient scratch item to subagent private memory overlay",
)
def append_subagent_ephemeral_item(
    payload: AppendSubagentEphemeralRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> SubagentOverlayStatusResponseDTO:
    """Write intermediate trial item into subagent overlay without polluting parent memory."""
    is_appended = service.append_subagent_ephemeral(payload.overlay_id, payload.item)
    return SubagentOverlayStatusResponseDTO(overlay_id=payload.overlay_id, is_success=is_appended)


@router.get(
    "/isolation/subagent/view/{overlay_id}",
    response_model=list[FlushItemDTO],
    status_code=status.HTTP_200_OK,
    summary="Retrieve composite memory view for subagent sandbox",
)
def get_subagent_memory_view(
    overlay_id: str,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> list[FlushItemDTO]:
    """Retrieve combined view consisting of parent read-only items and subagent ephemeral overlay."""
    return service.get_subagent_view(overlay_id)


@router.post(
    "/isolation/subagent/merge",
    response_model=list[FlushItemDTO],
    status_code=status.HTTP_200_OK,
    summary="Selectively harvest high-value findings from subagent overlay back to parent",
)
def merge_selective_subagent_findings(
    payload: MergeSelectiveRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> list[FlushItemDTO]:
    """Harvest chosen findings from subagent scratchpad and auto-purge remaining noise."""
    return service.merge_selective_to_parent(payload.overlay_id, payload.selected_item_ids)


@router.delete(
    "/isolation/subagent/overlay/{overlay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Purge a subagent ephemeral memory overlay sandbox",
)
def purge_subagent_overlay(
    overlay_id: str,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> None:
    """Manually purge and drop all transient scratch items for a subagent overlay."""
    service.purge_subagent_overlay(overlay_id)


@router.post(
    "/isolation/cron/sanitize",
    response_model=StatelessCronSanitizeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Cleanse prompt for stateless automated cron task execution",
)
def sanitize_stateless_cron_prompt(
    payload: StatelessCronSanitizeRequestDTO,
    service: MemorySubagentIsolationService = Depends(get_memory_subagent_isolation_service),
) -> StatelessCronSanitizeResponseDTO:
    """Strip user profile blocks and verify self-contained prompts to prevent task contamination."""
    return service.sanitize_cron_task_prompt(payload)
