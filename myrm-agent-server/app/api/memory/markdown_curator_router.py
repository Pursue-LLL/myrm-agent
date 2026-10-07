# [POS]: app/api/memory/markdown_curator_router.py
# [INPUT]: app.schemas.markdown_curator, app.services.memory.markdown_curator_service
# [OUTPUT]: router (FastAPI APIRouter for Markdown bidi-sync and Curator Studio)

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.schemas.markdown_curator import (
    AuditEntryRequest,
    CuratedMemoryEntryDTO,
    CurateEntryRequest,
    CuratorStudioSummaryDTO,
    MarkdownSyncRequest,
    MarkdownSyncResponseDTO,
    UpdateCurateEntryRequest,
)
from app.services.memory.markdown_curator_service import (
    MarkdownCuratorService,
    get_markdown_curator_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curator", tags=["Markdown Bidi-Sync & Memory Curator Studio"])


@router.post(
    "/entries",
    response_model=CuratedMemoryEntryDTO,
    summary="Create a curated memory entry",
)
async def create_entry(
    request: CurateEntryRequest,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> CuratedMemoryEntryDTO:
    """Create a new human-readable curated memory entry."""
    return service.create_entry(request)


@router.get(
    "/entries",
    response_model=list[CuratedMemoryEntryDTO],
    summary="List curated memory entries",
)
async def list_entries(
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
    category: str | None = Query(default=None, description="Filter by category"),
    status: str | None = Query(default=None, description="Filter by status"),
) -> list[CuratedMemoryEntryDTO]:
    """Retrieve memory entries matching optional category or status filters."""
    return service.list_entries(category=category, status=status)


@router.get(
    "/entries/{entry_id}",
    response_model=CuratedMemoryEntryDTO,
    summary="Get a curated memory entry by id",
)
async def get_entry(
    entry_id: str,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> CuratedMemoryEntryDTO:
    """Retrieve a single curated memory entry."""
    entry = service.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found.")
    return entry


@router.put(
    "/entries/{entry_id}",
    response_model=CuratedMemoryEntryDTO,
    summary="Update an existing curated memory entry",
)
async def update_entry(
    entry_id: str,
    request: UpdateCurateEntryRequest,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> CuratedMemoryEntryDTO:
    """Update title, content, status, or tags of a curated memory entry."""
    try:
        return service.update_entry(entry_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/entries/{entry_id}/audit",
    response_model=CuratedMemoryEntryDTO,
    summary="Audit (approve or reject) a memory candidate",
)
async def audit_entry(
    entry_id: str,
    request: AuditEntryRequest,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> CuratedMemoryEntryDTO:
    """Approve or reject a memory candidate to confirm or remove."""
    try:
        return service.audit_entry(entry_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/entries/{entry_id}",
    summary="One-click privacy wipe: erase a memory entry",
)
async def erase_entry(
    entry_id: str,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
    hard_erase: bool = Query(default=True, description="True for hard delete"),
) -> dict[str, bool]:
    """Wipe an entry permanently or archive it."""
    success = service.erase_entry(entry_id, hard_erase=hard_erase)
    if not success:
        raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found.")
    return {"is_success": True}


@router.post(
    "/sync",
    response_model=MarkdownSyncResponseDTO,
    summary="Sync from raw Markdown document",
)
async def sync_from_markdown(
    request: MarkdownSyncRequest,
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> MarkdownSyncResponseDTO:
    """Synchronize studio in-memory store with Markdown document with human-in-the-loop precedence."""
    return service.sync_from_markdown(request)


@router.get(
    "/summary",
    response_model=CuratorStudioSummaryDTO,
    summary="Get curator studio metrics summary",
)
async def get_summary(
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
) -> CuratorStudioSummaryDTO:
    """Aggregate total entries, confirmed/pending counts, and category breakdown."""
    return service.get_summary()


@router.get(
    "/export",
    summary="Export curated memories as formatted Markdown",
)
async def export_markdown(
    service: Annotated[MarkdownCuratorService, Depends(get_markdown_curator_service)],
    title: str = Query(default="Workspace Memory Mirror", description="Document title"),
) -> Response:
    """Render active memories into a downloadable/viewable Markdown document."""
    text = service.export_markdown(doc_title=title)
    return Response(content=text, media_type="text/markdown")
