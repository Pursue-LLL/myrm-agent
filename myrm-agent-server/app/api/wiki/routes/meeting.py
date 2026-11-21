"""[INPUT]
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.)
- app.services.meeting_notes.service::publish_meeting_notes (POS: Business orchestration facade for the meeting-notes pipeline. Delegates distillation to the chat agent LLM and publication to the wiki raw pipeline.)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian / source_sync / clip / knowledge_pack) live under this package and expose their own facades.)
- app.services.meeting_notes.live_notes::LiveNotesSnapshot / get_live_notes_registry (POS: Business orchestration layer for live meeting notes. Consumes *finalized* transcript lines from the existing streaming STT path, keeps the running transcript, and periodically produces rolling structured notes (summary / decisions / action items) through the shared minutes distillation.)

[OUTPUT]
- LiveNotesIngestRequest: LiveNotesIngestRequest
- LiveNotesSnapshotResponse: LiveNotesSnapshotResponse
- _live_notes_response: _live_notes_response
- ingest_live_meeting_transcript: Ingest one finalized transcript chunk; refresh rolling notes when due.
- finalize_live_meeting: Force a final distillation, publish minutes to the wiki, and release the session.

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.services.meeting_notes.live_notes import (
    LiveNotesSnapshot,
    get_live_notes_registry,
)
from app.services.meeting_notes.service import publish_meeting_notes
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


class LiveNotesIngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Finalized transcript chunk")
    timestamp: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Seconds since session start; must be finite",
    )
    line_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Client-generated id of this transcript line; replays are ignored",
    )

    @field_validator("text")
    @classmethod
    def _reject_blank_line(cls, value: str) -> str:
        # A blank line would be silently dropped by the session; reject it here so the
        # caller learns its utterance never reached the minutes.
        if not value.strip():
            raise ValueError("text must contain a non-blank transcript line")
        return value.strip()


class LiveNotesSnapshotResponse(BaseModel):
    success: bool = True
    session_id: str
    line_count: int
    transcript_chars: int
    refreshed: bool = False
    title: str = ""
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    debate_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    action_items: list[dict[str, str | None]] = Field(default_factory=list)
    published_wiki_paths: list[str] = Field(default_factory=list)
    error: str = ""


def _live_notes_response(
    snap: LiveNotesSnapshot,
    *,
    refreshed: bool,
    published: list[str] | None = None,
) -> LiveNotesSnapshotResponse:
    notes = snap.notes
    return LiveNotesSnapshotResponse(
        session_id=snap.session_id,
        line_count=snap.line_count,
        transcript_chars=snap.transcript_chars,
        refreshed=refreshed,
        title=notes.title if notes else "",
        summary=notes.summary if notes else "",
        decisions=list(notes.decisions) if notes else [],
        debate_points=list(notes.debate_points) if notes else [],
        risks=list(notes.risks) if notes else [],
        action_items=(
            [{"description": item.description, "owner": item.owner, "due_hint": item.due_hint} for item in notes.action_items]
            if notes
            else []
        ),
        published_wiki_paths=published or [],
    )


@router.post("/meeting-notes/live/{session_id}/ingest", response_model=LiveNotesSnapshotResponse)
async def ingest_live_meeting_transcript(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    session_id: str,
    payload: LiveNotesIngestRequest,
) -> LiveNotesSnapshotResponse:
    """Ingest one finalized transcript chunk; refresh rolling notes when due."""
    try:
        session = await get_live_notes_registry().get_or_create(session_id)
        if not session.ingest(payload.text, payload.timestamp, line_id=payload.line_id):
            return _live_notes_response(session.snapshot(), refreshed=False)
        refreshed = None
        try:
            refreshed = await session.maybe_refresh(archiver._llm)
        except Exception:
            # A transient distillation failure must not fail the ingest itself: the
            # line is already recorded and the last good snapshot is returned.
            logger.warning("Live meeting refresh failed; returning last snapshot", exc_info=True)
        return _live_notes_response(session.snapshot(), refreshed=refreshed is not None)
    except Exception as e:
        logger.exception("Live meeting ingest failed")
        raise HTTPException(status_code=500, detail="Live meeting ingest failed") from e


@router.post("/meeting-notes/live/{session_id}/finalize", response_model=LiveNotesSnapshotResponse)
async def finalize_live_meeting(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    session_id: str,
    auto_compile: bool = Query(True),
) -> LiveNotesSnapshotResponse:
    """Force a final distillation, publish minutes to the wiki, and release the session.

    Concurrent calls for one session share a single run, so the meeting is published once;
    a failed run leaves the session intact so the call can be retried.
    """
    registry = get_live_notes_registry()
    session = await registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Live meeting session not found")
    publish = partial(
        publish_meeting_notes,
        archiver._structure,
        auto_compile=auto_compile,
        compiler_enqueue=archiver._compiler._queue,
    )
    try:
        finalized = await session.finalize(archiver._llm, publish)
    except Exception as e:
        logger.exception("Live meeting finalize failed")
        raise HTTPException(status_code=500, detail="Live meeting finalize failed") from e
    await registry.drop(session_id)
    return _live_notes_response(finalized.snapshot, refreshed=True, published=list(finalized.published_paths))
