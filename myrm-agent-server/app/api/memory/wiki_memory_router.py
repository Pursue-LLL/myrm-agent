"""
[POS] app/api/memory/wiki_memory_router.py
[INPUT] app/schemas/wiki_memory.py, app/services/memory/wiki_memory_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.wiki_memory import (
    WikiBacklinkListResponse,
    WikiHistoryListResponse,
    WikiMemoryPageDTO,
    WikiMemoryPageInput,
    WikiRebuildIndexResponse,
    WikiRevertRequest,
    WikiRevertResponse,
    WikiSearchRequest,
    WikiSearchResponse,
)
from app.services.memory.wiki_memory_service import (
    WikiMemoryService,
    get_wiki_memory_service,
)

router = APIRouter(prefix="/wiki", tags=["wiki_memory"])


@router.post(
    "/pages",
    response_model=WikiMemoryPageDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a Markdown memory page with automatic Git version commit",
)
def save_page(
    payload: WikiMemoryPageInput,
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiMemoryPageDTO:
    """Persist page as Markdown SSOT, update derived FTS index, and create Git commit."""
    page_dto, _ = service.save_page(payload)
    return page_dto


@router.get(
    "/pages/{page_id}",
    response_model=WikiMemoryPageDTO,
    summary="Get a Markdown memory page directly from physical SSOT storage",
)
def get_page(
    page_id: str,
    scope: str = Query(default="global", description="Scope: 'global' or 'agent'"),
    profile_id: str | None = Query(default=None, description="Profile ID if agent-scoped"),
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiMemoryPageDTO:
    """Fetch page metadata and body from physical Markdown file."""
    page = service.get_page(page_id=page_id, scope=scope, profile_id=profile_id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wiki memory page not found: {page_id}",
        )
    return page


@router.delete(
    "/pages/{page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Markdown memory page, purge derived index, and commit deletion to Git",
)
def delete_page(
    page_id: str,
    scope: str = Query(default="global", description="Scope: 'global' or 'agent'"),
    profile_id: str | None = Query(default=None, description="Profile ID if agent-scoped"),
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> None:
    """Delete Markdown file and purge derived index entries."""
    deleted = service.delete_page(page_id=page_id, scope=scope, profile_id=profile_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wiki memory page not found: {page_id}",
        )


@router.get(
    "/pages",
    response_model=list[WikiMemoryPageDTO],
    summary="List Markdown memory pages matching scope filters",
)
def list_pages(
    scope: str | None = Query(default=None, description="Scope filter: 'global' or 'agent'"),
    profile_id: str | None = Query(default=None, description="Agent profile ID filter"),
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> list[WikiMemoryPageDTO]:
    """List all Markdown pages matching scope."""
    return service.list_pages(scope=scope, profile_id=profile_id)


@router.post(
    "/search",
    response_model=WikiSearchResponse,
    summary="Execute accelerated full-text search against the derived SQLite FTS5 index",
)
def search_pages(
    payload: WikiSearchRequest,
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiSearchResponse:
    """Full-text search powered by derived SQLite FTS5 table with scope filtering."""
    return service.search(payload)


@router.get(
    "/backlinks/{page_title}",
    response_model=WikiBacklinkListResponse,
    summary="Query incoming Obsidian-style backlinks referencing a target page title",
)
def get_backlinks(
    page_title: str,
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiBacklinkListResponse:
    """Query bidirectional link relationships across Markdown memory pages."""
    return service.get_backlinks(target_page_title=page_title)


@router.get(
    "/history",
    response_model=WikiHistoryListResponse,
    summary="Retrieve recent Git version audit commits for memory modifications",
)
def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiHistoryListResponse:
    """Audit log of Git commits recording memory page mutations."""
    return service.get_history(limit=limit)


@router.post(
    "/revert",
    response_model=WikiRevertResponse,
    summary="Revert an erroneous memory commit using Git revert",
)
def revert_commit(
    payload: WikiRevertRequest,
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiRevertResponse:
    """Roll back hallucinated or erroneous memory mutations and synchronize derived index."""
    resp = service.revert(commit_hash=payload.commit_hash)
    if not resp.reverted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to revert commit: {payload.commit_hash}",
        )
    return resp


@router.post(
    "/rebuild-index",
    response_model=WikiRebuildIndexResponse,
    summary="Rebuild the derived SQLite FTS5 index 100% idempotently from Markdown SSOT",
)
def rebuild_index(
    service: WikiMemoryService = Depends(get_wiki_memory_service),
) -> WikiRebuildIndexResponse:
    """Purge and reconstruct SQLite FTS5 index directly from physical Markdown files."""
    return service.rebuild_index()
