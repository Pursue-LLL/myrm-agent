"""FastAPI router for Lightweight Fusen Shared State Sync (Item 63).

[INPUT]
- app.schemas.fusen::{
    PostFusenNoteRequest, ResolveFusenNoteRequest, FusenCategoryDTOEnum,
  }
- app.services.agent.fusen_service::FusenSharedStateService

[OUTPUT]
- REST endpoints under /agents/fusen for posting, resolving, and querying shared sticky notes.

[POS]
- HTTP API layer for Item 63 Fusen shared sticky-note protocol.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.fusen import (
    FusenCategoryDTOEnum,
    PostFusenNoteRequest,
    ResolveFusenNoteRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.fusen_service import FusenSharedStateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/fusen",
    tags=["Lightweight Fusen Shared State Sync"],
)


@router.post(
    "/notes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Post a lightweight shared state sticky note",
)
async def post_note(req: PostFusenNoteRequest) -> StandardSuccessResponse:
    """Post an active state sticky note onto the decentralized team board."""
    try:
        note_dto = FusenSharedStateService.post_note(req)
        return create_success_response(data=note_dto.model_dump())
    except Exception as exc:
        logger.exception("Failed to post Fusen sticky note: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/notes/{note_id}/resolve",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve an active sticky note",
)
async def resolve_note(note_id: str, req: ResolveFusenNoteRequest) -> StandardSuccessResponse:
    """Mark an active sticky note as resolved with optional explanation."""
    try:
        note_dto = FusenSharedStateService.resolve_note(note_id, req)
        return create_success_response(data=note_dto.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/notes/{note_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific sticky note",
)
async def get_note(note_id: str) -> StandardSuccessResponse:
    """Retrieve an individual Fusen sticky note by its ID."""
    try:
        note_dto = FusenSharedStateService.get_note(note_id)
        return create_success_response(data=note_dto.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/notes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List sticky notes with multi-dimensional filters",
)
async def list_notes(
    session_id: str | None = Query(default=None),
    category: FusenCategoryDTOEnum | None = Query(default=None),
    tag_prefix: str | None = Query(default=None),
    include_resolved: bool = Query(default=False),
) -> StandardSuccessResponse:
    """Filter and list active or resolved sticky notes."""
    notes = FusenSharedStateService.list_notes(
        session_id=session_id,
        category=category,
        tag_prefix=tag_prefix,
        include_resolved=include_resolved,
    )
    return create_success_response(data=[n.model_dump() for n in notes])


@router.get(
    "/blockers",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Check active blockers in sub-millisecond latency",
)
async def check_blockers(
    session_id: str = Query(..., min_length=1),
    target_agent_id: str | None = Query(default=None),
) -> StandardSuccessResponse:
    """Rapidly inspect active blocker sticky notes without invoking LLM tokens."""
    summary = FusenSharedStateService.check_blockers(
        session_id=session_id,
        target_agent_id=target_agent_id,
    )
    return create_success_response(data=summary.model_dump())


@router.post(
    "/cleanup-expired",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Prune expired sticky notes",
)
async def cleanup_expired() -> StandardSuccessResponse:
    """Prune sticky notes whose TTL has lapsed."""
    pruned_count = FusenSharedStateService.cleanup_expired()
    return create_success_response(data={"pruned_count": pruned_count})
