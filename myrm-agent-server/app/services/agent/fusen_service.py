"""Service layer for Lightweight Fusen Shared State Sync (Item 63).

[INPUT]
- PostFusenNoteRequest, ResolveFusenNoteRequest schemas.
- FusenSharedBoard from harness.

[OUTPUT]
- FusenNoteDTO, FusenBlockerSummaryDTO.

[POS]
- Bridge between FastAPI fusen router and underlying harness FusenSharedBoard engine.
"""

from __future__ import annotations

import threading
import uuid
from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.fusen import (
    FusenBlockerSummary,
    FusenCategory,
    FusenNote,
    FusenSharedBoard,
)

from app.schemas.fusen import (
    FusenBlockerSummaryDTO,
    FusenCategoryDTOEnum,
    FusenNoteDTO,
    NoteStatusDTOEnum,
    PostFusenNoteRequest,
    ResolveFusenNoteRequest,
)


class FusenSharedStateService:
    """Thread-safe orchestration service managing shared state sticky notes."""

    _board: ClassVar[FusenSharedBoard] = FusenSharedBoard()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _to_note_dto(cls, n: FusenNote) -> FusenNoteDTO:
        return FusenNoteDTO(
            note_id=n.note_id,
            session_id=n.session_id,
            author_agent_id=n.author_agent_id,
            category=FusenCategoryDTOEnum(n.category.value),
            tag=n.tag,
            content=n.content,
            metadata=dict(n.metadata),
            status=NoteStatusDTOEnum(n.status.value),
            resolution_note=n.resolution_note,
            ttl_seconds=n.ttl_seconds,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )

    @classmethod
    def _to_summary_dto(cls, s: FusenBlockerSummary) -> FusenBlockerSummaryDTO:
        return FusenBlockerSummaryDTO(
            is_blocked=s.is_blocked,
            blocker_count=s.blocker_count,
            blockers=[cls._to_note_dto(b) for b in s.blockers],
            active_tags=list(s.active_tags),
        )

    @classmethod
    def post_note(cls, req: PostFusenNoteRequest) -> FusenNoteDTO:
        """Post a new sticky note to the shared board."""
        note_id = req.note_id or f"fusen-{uuid.uuid4().hex[:8]}"
        category = FusenCategory(req.category.value)
        with cls._lock:
            note = cls._board.post_note(
                note_id=note_id,
                session_id=req.session_id,
                author_agent_id=req.author_agent_id,
                category=category,
                tag=req.tag,
                content=req.content,
                metadata=req.metadata,
                ttl_seconds=req.ttl_seconds,
            )
        return cls._to_note_dto(note)

    @classmethod
    def resolve_note(cls, note_id: str, req: ResolveFusenNoteRequest) -> FusenNoteDTO:
        """Mark an active sticky note as resolved."""
        with cls._lock:
            note = cls._board.resolve_note(
                note_id=note_id,
                resolution_note=req.resolution_note,
            )
        return cls._to_note_dto(note)

    @classmethod
    def get_note(cls, note_id: str) -> FusenNoteDTO:
        """Retrieve a sticky note by ID."""
        with cls._lock:
            note = cls._board.get_note(note_id)
        if note is None:
            msg = f"Fusen note '{note_id}' not found."
            raise KeyError(msg)
        return cls._to_note_dto(note)

    @classmethod
    def list_notes(
        cls,
        session_id: str | None = None,
        category: FusenCategoryDTOEnum | None = None,
        tag_prefix: str | None = None,
        include_resolved: bool = False,
    ) -> list[FusenNoteDTO]:
        """Query active or resolved sticky notes matching criteria."""
        cat_enum = FusenCategory(category.value) if category is not None else None
        with cls._lock:
            notes = cls._board.list_notes(
                session_id=session_id,
                category=cat_enum,
                tag_prefix=tag_prefix,
                include_resolved=include_resolved,
            )
        return [cls._to_note_dto(n) for n in notes]

    @classmethod
    def check_blockers(
        cls,
        session_id: str,
        target_agent_id: str | None = None,
    ) -> FusenBlockerSummaryDTO:
        """Sub-millisecond query for active blockers."""
        with cls._lock:
            summary = cls._board.check_blockers(
                session_id=session_id,
                target_agent_id=target_agent_id,
            )
        return cls._to_summary_dto(summary)

    @classmethod
    def cleanup_expired(cls) -> int:
        """Prune expired sticky notes."""
        with cls._lock:
            return cls._board.cleanup_expired()

    @classmethod
    def clear(cls) -> None:
        """Reset service in-memory state."""
        with cls._lock:
            cls._board.clear()
