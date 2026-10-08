"""REST endpoints for session lineage discovery search, cron demotion, and hydration.

[POS]
app/api/memory/lineage_search_router.py

[INPUT]
- FastAPI APIRouter, Depends, HTTPException, and lineage search DTOs

[OUTPUT]
- REST endpoints for session lineage discovery search, cron demotion, and hydration
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    ConversationMessage,
    SessionMeta,
    SessionSourceKind,
)

from app.schemas.lineage_search import (
    AddMessageRequestDTO,
    AddMessageResponseDTO,
    AddSessionRequestDTO,
    AddSessionResponseDTO,
    ConversationMessageDTO,
    HydratedSessionHitDTO,
    LineageSearchRequestDTO,
    LineageSearchResponseDTO,
    LineageSearchStatsDTO,
)
from app.services.memory.lineage_search_service import (
    LineageSearchService,
    get_lineage_search_service,
)

router = APIRouter(prefix="/lineage-search", tags=["lineage-search"])


@router.post("/sessions", response_model=AddSessionResponseDTO)
def add_session(
    payload: AddSessionRequestDTO,
    service: LineageSearchService = Depends(get_lineage_search_service),
) -> AddSessionResponseDTO:
    """Register or update session metadata in the lineage catalog."""
    try:
        source_enum = SessionSourceKind(payload.session.source)
    except ValueError:
        source_enum = SessionSourceKind.INTERACTIVE

    meta = SessionMeta(
        session_id=payload.session.session_id,
        title=payload.session.title,
        source=source_enum,
        lineage_root_id=payload.session.lineage_root_id,
        parent_session_id=payload.session.parent_session_id,
        model=payload.session.model,
        started_at=payload.session.started_at,
    )
    service.add_session(meta)
    return AddSessionResponseDTO(
        session_id=meta.session_id,
        is_success=True,
    )


@router.post("/messages", response_model=AddMessageResponseDTO)
def add_message(
    payload: AddMessageRequestDTO,
    service: LineageSearchService = Depends(get_lineage_search_service),
) -> AddMessageResponseDTO:
    """Record and index a conversation message."""
    msg = ConversationMessage(
        message_id=payload.message.message_id,
        session_id=payload.message.session_id,
        role=payload.message.role,
        content=payload.message.content,
        created_at=payload.message.created_at,
        sequence_num=payload.message.sequence_num,
    )
    service.add_message(msg)
    return AddMessageResponseDTO(
        message_id=msg.message_id,
        is_success=True,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[ConversationMessageDTO])
def get_session_messages(
    session_id: str,
    service: LineageSearchService = Depends(get_lineage_search_service),
) -> list[ConversationMessageDTO]:
    """Fetch all chronological messages for a specific session."""
    meta = service.get_session(session_id)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    messages = service.get_messages(session_id)
    return [
        ConversationMessageDTO(
            message_id=m.message_id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            sequence_num=m.sequence_num,
        )
        for m in messages
    ]


@router.post("/search", response_model=LineageSearchResponseDTO)
def search_lineage(
    payload: LineageSearchRequestDTO,
    service: LineageSearchService = Depends(get_lineage_search_service),
) -> LineageSearchResponseDTO:
    """Execute lineage-deduped discovery search with PR #19434 recall blindness defense."""
    hits = service.search(
        query=payload.query,
        limit=payload.limit,
        max_scan_limit=payload.max_scan_limit,
        include_hidden=payload.include_hidden,
        anchor_window=payload.anchor_window,
        bookend_count=payload.bookend_count,
    )

    def _convert_msgs(msgs: list[ConversationMessage]) -> list[ConversationMessageDTO]:
        return [
            ConversationMessageDTO(
                message_id=m.message_id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                sequence_num=m.sequence_num,
            )
            for m in msgs
        ]

    hit_dtos = [
        HydratedSessionHitDTO(
            session_id=h.session_id,
            lineage_root_id=h.lineage_root_id,
            title=h.title,
            source=h.source,
            score=h.score,
            match_message_id=h.match_message_id,
            snippet=h.snippet,
            detail_level=h.detail_level,
            deep_link=h.deep_link,
            window_messages=_convert_msgs(h.window_messages),
            bookend_start=_convert_msgs(h.bookend_start),
            bookend_end=_convert_msgs(h.bookend_end),
            messages_before=h.messages_before,
            messages_after=h.messages_after,
        )
        for h in hits
    ]

    return LineageSearchResponseDTO(
        query=payload.query,
        total_hits=len(hit_dtos),
        results=hit_dtos,
    )


@router.get("/stats", response_model=LineageSearchStatsDTO)
def get_lineage_search_stats(
    service: LineageSearchService = Depends(get_lineage_search_service),
) -> LineageSearchStatsDTO:
    """Retrieve operational telemetry of the session catalog."""
    stats = service.get_stats()
    return LineageSearchStatsDTO(
        total_sessions=stats.total_sessions,
        total_messages=stats.total_messages,
        hidden_sources_count=stats.hidden_sources_count,
        demoted_sources_count=stats.demoted_sources_count,
    )
