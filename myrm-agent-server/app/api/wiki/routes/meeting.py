"""[INPUT]
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.)
- app.channels.types::VoiceConfig (POS: Channel system domain types — pure data definitions, no I/O.)
- app.services.meeting_notes.service::process_meeting_audio / publish_meeting_notes (POS: Business orchestration facade for the Meeting Scribe pipeline. Delegates ASR to channels/voice/stt.py, distillation to the chat agent LLM, and publication to the wiki raw pipeline.)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian / source_sync / clip / knowledge_pack) live under this package and expose their own facades.)
- app.services.meeting_notes.live_notes::LiveNotesSession / get_live_notes_registry (POS: Business orchestration layer for live meeting notes. Consumes *finalized* transcript lines from the existing streaming STT path, keeps the running transcript, and periodically produces rolling structured notes (summary / decisions / action items) by reusing the batch distillation prompt.)

[OUTPUT]
- MeetingNotesResponse: Response payload for meeting audio transcription pipeline.
- transcribe_meeting_audio: Chunked parallel ASR + LLM minutes distillation + wiki raw publish for one meeting audio upload.
- LiveNotesIngestRequest: LiveNotesIngestRequest
- LiveNotesSnapshotResponse: LiveNotesSnapshotResponse
- _live_notes_response: _live_notes_response
- ingest_live_meeting_transcript: Ingest one finalized transcript chunk; refresh rolling notes when due.
- get_live_meeting_snapshot: Return the current rolling notes snapshot for a live meeting.
- finalize_live_meeting: Force a final distillation, publish minutes to the wiki, and release the session.

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.channels.types import VoiceConfig
from app.services.meeting_notes.service import process_meeting_audio
from app.services.wiki import MemoryToWikiArchiver

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


class MeetingNotesResponse(BaseModel):
    """Response payload for meeting audio transcription pipeline."""

    success: bool
    chunk_count: int = 0
    duration_seconds: float = 0.0
    title: str = ""
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    debate_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    action_items: list[dict[str, str | None]] = Field(default_factory=list)
    published_wiki_paths: list[str] = Field(default_factory=list)
    error: str = ""


@router.post("/meeting-notes/transcribe", response_model=MeetingNotesResponse)
async def transcribe_meeting_audio(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="Long meeting audio upload"),
    chunk_seconds: int = Query(600, ge=60, le=1800),
    max_parallel: int = Query(3, ge=1, le=8),
    auto_compile: bool = Query(True),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> MeetingNotesResponse:
    """Chunked parallel ASR + LLM minutes distillation + wiki raw publish for one meeting audio upload."""
    _MAX_AUDIO_BYTES = 500 * 1024 * 1024
    allowed_suffixes = (".mp3", ".m4a", ".wav", ".webm", ".ogg", ".flac", ".opus")
    filename = file.filename or ""
    if not filename.lower().endswith(allowed_suffixes):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 500 MB)")
    try:
        with tempfile.TemporaryDirectory(prefix="myrm_meeting_upload_") as tmp_dir:
            audio_path = Path(tmp_dir) / f"meeting{Path(filename).suffix.lower()}"
            audio_path.write_bytes(audio_bytes)
            result = await process_meeting_audio(
                audio_path,
                voice_config=VoiceConfig(stt_enabled=True),
                llm=archiver._llm,
                structure=archiver._structure,
                chunk_seconds=chunk_seconds,
                max_parallel=max_parallel,
                auto_compile=auto_compile,
                compiler_enqueue=archiver._compiler._queue,
            )
            return MeetingNotesResponse(
                success=True,
                chunk_count=result.chunk_count,
                duration_seconds=result.duration_seconds,
                title=result.notes.title,
                summary=result.notes.summary,
                decisions=list(result.notes.decisions),
                debate_points=list(result.notes.debate_points),
                risks=list(result.notes.risks),
                action_items=[
                    {"description": i.description, "owner": i.owner, "due_hint": i.due_hint} for i in result.notes.action_items
                ],
                published_wiki_paths=result.published_wiki_paths,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Meeting notes transcription failed: %s", e)
        raise HTTPException(status_code=500, detail="Meeting notes transcription failed") from e


from app.services.meeting_notes.live_notes import (  # noqa: E402
    LiveNotesSession,
    get_live_notes_registry,
)
from app.services.meeting_notes.service import publish_meeting_notes  # noqa: E402


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
    session: LiveNotesSession,
    *,
    refreshed: bool,
    published: list[str] | None = None,
) -> LiveNotesSnapshotResponse:
    snap = session.snapshot()
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
            return _live_notes_response(session, refreshed=False)
        refreshed = None
        try:
            refreshed = await session.maybe_refresh(archiver._llm)
        except Exception:
            # A transient distillation failure must not fail the ingest itself: the
            # line is already recorded and the last good snapshot is returned.
            logger.warning("Live meeting refresh failed; returning last snapshot", exc_info=True)
        return _live_notes_response(session, refreshed=refreshed is not None)
    except Exception as e:
        logger.error("Live meeting ingest failed: %s", e)
        raise HTTPException(status_code=500, detail="Live meeting ingest failed") from e


@router.get("/meeting-notes/live/{session_id}", response_model=LiveNotesSnapshotResponse)
async def get_live_meeting_snapshot(session_id: str) -> LiveNotesSnapshotResponse:
    """Return the current rolling notes snapshot for a live meeting."""
    session = await get_live_notes_registry().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Live meeting session not found")
    return _live_notes_response(session, refreshed=False)


@router.post("/meeting-notes/live/{session_id}/finalize", response_model=LiveNotesSnapshotResponse)
async def finalize_live_meeting(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    session_id: str,
    auto_compile: bool = Query(True),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> LiveNotesSnapshotResponse:
    """Force a final distillation, publish minutes to the wiki, and release the session."""
    registry = get_live_notes_registry()
    session = await registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Live meeting session not found")
    try:
        await session.refresh(archiver._llm)
        snapshot = session.snapshot()
        published: list[str] = []
        if snapshot.notes is not None:
            published = await publish_meeting_notes(
                archiver._structure,
                snapshot.notes,
                session.render_transcript(),
                agent_id,
                auto_compile,
                archiver._compiler._queue,
            )
        response = _live_notes_response(session, refreshed=True, published=published)
        await registry.drop(session_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Live meeting finalize failed: %s", e)
        raise HTTPException(status_code=500, detail="Live meeting finalize failed") from e
