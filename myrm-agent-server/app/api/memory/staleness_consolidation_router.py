"""FastAPI router for Auto Memory Staleness Decay and Consolidation Audit Suite (Item 158).

[INPUT]
- RegisterMemoryRequest, TouchRecallRequest, RunAuditRequest, ApplyConsolidationRequest, ArchiveMemoriesRequest.

[OUTPUT]
- MemoryItemProfileDTO, MemoryAuditReportDTO, and status update payloads.

[POS]
- Router endpoints in myrm-agent-server/app/api/memory/staleness_consolidation_router.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.staleness_consolidation import (
    ApplyConsolidationRequest,
    ArchiveMemoriesRequest,
    MemoryAuditReportDTO,
    MemoryItemProfileDTO,
    MemoryStatusDTO,
    RegisterMemoryRequest,
    RunAuditRequest,
    TouchRecallRequest,
)
from app.services.memory.staleness_consolidation_service import (
    StalenessConsolidationService,
)

router = APIRouter(
    prefix="/staleness-consolidation", tags=["memory-staleness-consolidation"]
)
_service = StalenessConsolidationService()


def get_staleness_consolidation_service() -> StalenessConsolidationService:
    """Dependency helper providing the active StalenessConsolidationService."""
    return _service


@router.post(
    "/memories",
    response_model=MemoryItemProfileDTO,
    status_code=status.HTTP_201_CREATED,
)
async def register_memory(
    req: RegisterMemoryRequest,
) -> MemoryItemProfileDTO:
    """Register an autonomous memory record for staleness and validity tracking."""
    return get_staleness_consolidation_service().register_memory(req)


@router.get(
    "/memories",
    response_model=list[MemoryItemProfileDTO],
)
async def list_memories(
    memory_status: MemoryStatusDTO | None = Query(
        default=None, alias="status", description="Optional status filter"
    ),
) -> list[MemoryItemProfileDTO]:
    """List tracked memory records, optionally filtered by lifecycle status."""
    return get_staleness_consolidation_service().list_memories(status=memory_status)


@router.get(
    "/memories/{memory_id}",
    response_model=MemoryItemProfileDTO,
)
async def get_memory(
    memory_id: str,
) -> MemoryItemProfileDTO:
    """Retrieve an individual memory profile by ID."""
    item = get_staleness_consolidation_service().get_memory(memory_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record {memory_id} not found",
        )
    return item


@router.post(
    "/touch-recall",
    response_model=MemoryItemProfileDTO,
)
async def touch_recall(
    req: TouchRecallRequest,
) -> MemoryItemProfileDTO:
    """Record a recall touch event, resetting decay time and incrementing hit frequency."""
    item = get_staleness_consolidation_service().touch_recall(req)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record {req.memory_id} not found",
        )
    return item


@router.post(
    "/audit",
    response_model=MemoryAuditReportDTO,
)
async def run_memory_audit(
    req: RunAuditRequest,
) -> MemoryAuditReportDTO:
    """Run an end-to-end memory health audit: decay profiling, repo checks, and consolidation."""
    return get_staleness_consolidation_service().run_audit(req)


@router.post(
    "/consolidate",
    response_model=MemoryItemProfileDTO,
)
async def apply_consolidation(
    req: ApplyConsolidationRequest,
) -> MemoryItemProfileDTO:
    """Approve and execute a consolidation proposal to merge fragmented rules."""
    new_item = get_staleness_consolidation_service().apply_consolidation(req)
    if new_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal {req.proposal_id} not found",
        )
    return new_item


@router.post(
    "/archive",
    response_model=list[str],
)
async def archive_memories(
    req: ArchiveMemoriesRequest,
) -> list[str]:
    """Safely archive stale or invalidated memory records."""
    return get_staleness_consolidation_service().archive_memories(req)
