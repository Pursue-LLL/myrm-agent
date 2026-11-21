"""Live (in-meeting) notes session orchestration.

[INPUT]
- app.services.meeting_notes.models::StructuredMeetingNotes (POS: SSOT minutes payload)
- app.services.meeting_notes.service::distill_meeting_notes (POS: LLM minutes distillation)

[OUTPUT]
- LiveNotesSession: in-memory live meeting session (transcript ingestion + rolling structured notes + run-once finalize)
- LiveNotesSnapshot: serializable snapshot returned to the client
- FinalizedMeeting: final snapshot plus the vault paths the minutes were published to
- MinutesPublisher: callback that publishes final minutes and returns the written vault paths
- LiveNotesRegistry: process-local session registry

[POS]
Business orchestration layer for live meeting notes. Consumes *finalized* transcript
lines from the existing streaming STT path, keeps the running transcript, and
periodically produces rolling structured notes (summary / decisions / action items)
through the shared minutes distillation. Contains no ASR implementation and no
framework code; it is a thin, deterministic scheduler around the existing distillation.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.meeting_notes.models import StructuredMeetingNotes
from app.services.meeting_notes.service import distill_meeting_notes

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

# Default cadence: refresh the rolling notes at most once per interval, and only when
# enough new speech accumulated. Time-based (not per-line) to bound LLM cost during
# long meetings.
_DEFAULT_REFRESH_SECONDS = 120.0
_DEFAULT_MIN_NEW_CHARS = 200
_MAX_TRANSCRIPT_CHARS = 120_000
# Upper bound on remembered line ids. The dedupe window only has to outlive a retried
# request, so a small ring is enough; bounding it keeps long meetings memory-flat.
_DEDUPE_WINDOW = 512


@dataclass(frozen=True)
class LiveNotesSnapshot:
    """Serializable view of a live meeting session and its latest structured notes."""

    session_id: str
    line_count: int
    transcript_chars: int
    started_at: float
    last_refreshed_at: float | None
    notes: StructuredMeetingNotes | None


@dataclass(frozen=True)
class FinalizedMeeting:
    """Final snapshot of a finished meeting and the vault paths its minutes were written to."""

    snapshot: LiveNotesSnapshot
    published_paths: tuple[str, ...]


# Publishes the final minutes (notes, rendered transcript) and returns the vault-relative
# paths that were actually written. Supplied by the caller, which owns the target vault.
MinutesPublisher = Callable[[StructuredMeetingNotes, str], Awaitable[list[str]]]


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
        clock: Callable[[], float] = time.monotonic,
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
        self._seen_line_ids: dict[str, None] = {}
        self._lock = asyncio.Lock()
        self._finalizing: asyncio.Task[FinalizedMeeting] | None = None

    # -- ingestion ---------------------------------------------------------
    def ingest(self, text: str, timestamp: float | None = None, *, line_id: str | None = None) -> bool:
        """Append a finalized transcript line. Returns True when it was recorded.

        ``timestamp`` is seconds since session start; when omitted the session-relative
        wall time is derived from the injected clock (never the raw clock value, which
        would render as meaningless absolute minutes).

        ``line_id`` makes ingestion idempotent under at-least-once delivery: a replayed
        request (client retry, proxy replay) carrying an id already seen in this session
        is ignored instead of duplicating the line in the transcript and the minutes.
        Identifiers are only compared, never stored beyond ``_DEDUPE_WINDOW``.
        """
        cleaned = text.strip()
        if not cleaned:
            return False
        if line_id is not None and line_id in self._seen_line_ids:
            return False
        if line_id is not None:
            self._seen_line_ids[line_id] = None
            if len(self._seen_line_ids) > _DEDUPE_WINDOW:
                del self._seen_line_ids[next(iter(self._seen_line_ids))]
        raw_ts = float(timestamp) if timestamp is not None else float(self._clock()) - self._started_at
        # A non-finite stamp would render as ``[nan:..]`` and, for an infinite one, make
        # ``inf // 60`` NaN and raise when formatting; clamp it at the only write point.
        ts = raw_ts if math.isfinite(raw_ts) else 0.0
        self._lines.append(_TranscriptLine(timestamp=max(0.0, ts), text=cleaned))
        self._chars_since_refresh += len(cleaned)
        return True

    # -- state -------------------------------------------------------------
    @property
    def started_at(self) -> float:
        return self._started_at

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
    async def refresh(self, llm: BaseChatModel | None) -> LiveNotesSnapshot:
        """Force a rolling distillation over the transcript and return the snapshot."""
        async with self._lock:
            return await self._refresh_locked(llm)

    async def maybe_refresh(self, llm: BaseChatModel | None) -> LiveNotesSnapshot | None:
        """Refresh only when due; returns a snapshot on refresh, otherwise None.

        The due-ness re-check happens under the lock so concurrent ingests for the
        same session cannot trigger overlapping (and therefore redundant) LLM calls.
        """
        async with self._lock:
            if not self.should_refresh():
                return None
            return await self._refresh_locked(llm)

    async def _refresh_locked(self, llm: BaseChatModel | None) -> LiveNotesSnapshot:
        transcript = self.render_transcript()
        if transcript.strip():
            self._notes = await distill_meeting_notes(transcript, llm)
        self._last_refreshed_at = float(self._clock())
        self._chars_since_refresh = 0
        return self.snapshot()

    # -- finalization ------------------------------------------------------
    async def finalize(self, llm: BaseChatModel | None, publish: MinutesPublisher) -> FinalizedMeeting:
        """Distill the final notes and publish them, once per session.

        Concurrent callers (a double stop, a retry racing a slow first attempt) share one
        run, so the meeting is published once. A failed run is forgotten so the next call
        retries on the intact session; a finished run is remembered so a caller that raced
        the registry release gets the same result instead of publishing again.
        """
        if self._finalizing is None:
            self._finalizing = asyncio.create_task(self._distill_and_publish(llm, publish))
            self._finalizing.add_done_callback(self._forget_failed_finalize)
        # shield: a caller that goes away must not cancel the run the other callers share.
        return await asyncio.shield(self._finalizing)

    async def _distill_and_publish(self, llm: BaseChatModel | None, publish: MinutesPublisher) -> FinalizedMeeting:
        await self.refresh(llm)
        snapshot = self.snapshot()
        published: list[str] = []
        if snapshot.notes is not None:
            published = await publish(snapshot.notes, self.render_transcript())
        return FinalizedMeeting(snapshot=snapshot, published_paths=tuple(published))

    def _forget_failed_finalize(self, task: asyncio.Task[FinalizedMeeting]) -> None:
        # Reading the exception also marks it retrieved, so a run nobody awaits any more stays quiet.
        if task.cancelled() or task.exception() is not None:
            self._finalizing = None


class LiveNotesRegistry:
    """Process-local registry of live meeting sessions (single-machine product model).

    Bounded to ``max_sessions``; when full, the oldest session (by start time) is
    evicted so a caller that never finalizes cannot grow the process unboundedly.
    """

    def __init__(self, *, max_sessions: int = 64) -> None:
        self._sessions: dict[str, LiveNotesSession] = {}
        self._lock = asyncio.Lock()
        self._max_sessions = max(1, max_sessions)

    async def get_or_create(
        self,
        session_id: str,
        *,
        refresh_seconds: float = _DEFAULT_REFRESH_SECONDS,
        min_new_chars: int = _DEFAULT_MIN_NEW_CHARS,
    ) -> LiveNotesSession:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                return session
            if len(self._sessions) >= self._max_sessions:
                oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].started_at)
                self._sessions.pop(oldest_id, None)
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
