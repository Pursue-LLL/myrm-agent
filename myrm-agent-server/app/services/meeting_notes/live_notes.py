"""Live (in-meeting) notes session orchestration.

[INPUT]
- app.services.meeting_notes.models::StructuredMeetingNotes (POS: SSOT minutes payload)
- app.services.meeting_notes.service::distill_meeting_notes (POS: LLM minutes distillation)

[OUTPUT]
- LiveNotesSession: in-memory live meeting session (transcript ingestion + rolling structured notes)
- LiveNotesSnapshot: serializable snapshot returned to the client
- LiveNotesRegistry: process-local session registry

[POS]
Business orchestration layer for live meeting notes. Consumes *finalized* transcript
lines from the existing streaming STT path, keeps the running transcript, and
periodically produces rolling structured notes (summary / decisions / action items)
by reusing the batch distillation prompt. Contains no ASR implementation and no
framework code; it is a thin, deterministic scheduler around the existing distillation.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.services.meeting_notes.models import StructuredMeetingNotes
from app.services.meeting_notes.service import distill_meeting_notes

# Default cadence: refresh the rolling notes at most once per interval, and only when
# enough new speech accumulated. Time-based (not per-line) to bound LLM cost during
# long meetings.
_DEFAULT_REFRESH_SECONDS = 120.0
_DEFAULT_MIN_NEW_CHARS = 200
_MAX_TRANSCRIPT_CHARS = 120_000


@dataclass(frozen=True)
class LiveNotesSnapshot:
    """Serializable view of a live meeting session and its latest structured notes."""

    session_id: str
    line_count: int
    transcript_chars: int
    started_at: float
    last_refreshed_at: float | None
    notes: StructuredMeetingNotes | None


@dataclass
class _TranscriptLine:
    timestamp: float
    text: str


class LiveNotesSession:
    """Running transcript + rolling structured notes for one live meeting.

    The session is intentionally single-flight: refreshes are serialized via an
    asyncio lock so concurrent ingest requests cannot trigger overlapping LLM calls.
    """

    def __init__(
        self,
        session_id: str,
        *,
        refresh_seconds: float = _DEFAULT_REFRESH_SECONDS,
        min_new_chars: int = _DEFAULT_MIN_NEW_CHARS,
        clock: object = time.monotonic,
    ) -> None:
        self.session_id = session_id
        self._refresh_seconds = max(1.0, refresh_seconds)
        self._min_new_chars = max(0, min_new_chars)
        self._clock = clock
        self._lines: list[_TranscriptLine] = []
        self._started_at = float(self._clock())
        self._last_refreshed_at: float | None = None
        self._chars_since_refresh = 0
        self._notes: StructuredMeetingNotes | None = None
        self._lock = asyncio.Lock()

    # -- ingestion ---------------------------------------------------------
    def ingest(self, text: str, timestamp: float | None = None) -> bool:
        """Append a finalized transcript line. Returns True when it was non-empty."""
        cleaned = text.strip()
        if not cleaned:
            return False
        ts = float(timestamp) if timestamp is not None else float(self._clock())
        self._lines.append(_TranscriptLine(timestamp=ts, text=cleaned))
        self._chars_since_refresh += len(cleaned)
        return True

    # -- state -------------------------------------------------------------
    @property
    def line_count(self) -> int:
        return len(self._lines)

    @property
    def transcript_chars(self) -> int:
        return sum(len(line.text) for line in self._lines)

    def render_transcript(self) -> str:
        """Render the running transcript with ``[mm:ss]`` wall-clock markers."""
        rendered = "\n".join(
            f"[{int(line.timestamp // 60):02d}:{int(line.timestamp % 60):02d}] {line.text}"
            for line in self._lines
        )
        # Bound the payload sent to the LLM; keep the most recent tail on overflow.
        return rendered[-_MAX_TRANSCRIPT_CHARS:]

    def should_refresh(self, now: float | None = None) -> bool:
        """True when the rolling refresh cadence and content threshold are both met."""
        if self._chars_since_refresh < self._min_new_chars:
            return False
        current = float(now) if now is not None else float(self._clock())
        if self._last_refreshed_at is None:
            return True
        return (current - self._last_refreshed_at) >= self._refresh_seconds

    def snapshot(self) -> LiveNotesSnapshot:
        return LiveNotesSnapshot(
            session_id=self.session_id,
            line_count=self.line_count,
            transcript_chars=self.transcript_chars,
            started_at=self._started_at,
            last_refreshed_at=self._last_refreshed_at,
            notes=self._notes,
        )

    # -- distillation ------------------------------------------------------
    async def refresh(self, llm: object) -> LiveNotesSnapshot:
        """Force a rolling distillation over the transcript and return the snapshot."""
        async with self._lock:
            transcript = self.render_transcript()
            if transcript.strip():
                self._notes = await distill_meeting_notes(transcript, llm)
            self._last_refreshed_at = float(self._clock())
            self._chars_since_refresh = 0
            return self.snapshot()

    async def maybe_refresh(self, llm: object) -> LiveNotesSnapshot | None:
        """Refresh only when due; returns a snapshot on refresh, otherwise None."""
        if not self.should_refresh():
            return None
        return await self.refresh(llm)


class LiveNotesRegistry:
    """Process-local registry of live meeting sessions (single-machine product model)."""

    def __init__(self) -> None:
        self._sessions: dict[str, LiveNotesSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        session_id: str,
        *,
        refresh_seconds: float = _DEFAULT_REFRESH_SECONDS,
        min_new_chars: int = _DEFAULT_MIN_NEW_CHARS,
    ) -> LiveNotesSession:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = LiveNotesSession(
                    session_id,
                    refresh_seconds=refresh_seconds,
                    min_new_chars=min_new_chars,
                )
                self._sessions[session_id] = session
            return session

    async def get(self, session_id: str) -> LiveNotesSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def drop(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)


_LIVE_NOTES_REGISTRY = LiveNotesRegistry()


def get_live_notes_registry() -> LiveNotesRegistry:
    """Return the process-local live notes registry singleton."""
    return _LIVE_NOTES_REGISTRY


__all__ = [
    "LiveNotesRegistry",
    "LiveNotesSession",
    "LiveNotesSnapshot",
    "get_live_notes_registry",
]
