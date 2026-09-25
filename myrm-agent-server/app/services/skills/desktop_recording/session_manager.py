"""Desktop recording session registry: retention, lifecycle and capture-loop ownership.

[INPUT]
- app.api.skills.desktop_recorder::schemas (POS: recording DTOs + session state container)
- app.services.skills.desktop_recording::capture_task (POS: AX capture loop lifecycle)

[OUTPUT]
- Session registry API: `create_session`, `lookup_session`, `stop_session`, `session_count`
- Retention policy: bounded finished-session history and a concurrent-capture budget

[POS]
Skill recording session lifecycle. Owns which sessions exist, which of them still capture, and
when an abandoned or surplus recording is released, so the API layer stays stateless.
"""

from __future__ import annotations

import logging
import time

from app.api.skills.desktop_recorder.schemas import RecordingSessionState
from app.services.skills.desktop_recording.capture_task import DesktopCaptureTask

logger = logging.getLogger(__name__)

# Retained finished sessions, newest last: a client may still fetch the summary or publish right
# after stopping, but old ones are evicted so memory cannot accumulate.
_MAX_RETAINED_SESSIONS = 8
# Concurrent capture loops are a native resource; keep the running set small so a misbehaving
# client cannot pin the host by starting recordings it never stops.
_MAX_CONCURRENT_CAPTURES = 2

# In-memory session store for recording sessions (bounded ring-buffer of events per session).
_SESSIONS: dict[str, RecordingSessionState] = {}
# Capture loops keyed by session id; stopped and dropped when the session ends.
_CAPTURE_TASKS: dict[str, DesktopCaptureTask] = {}


def session_count() -> int:
    """Number of tracked sessions (used by tests and diagnostics)."""
    return len(_SESSIONS)


def create_session(session_id: str, app_scope: str) -> RecordingSessionState:
    """Register a new recording session and start capturing for it."""
    session = RecordingSessionState(session_id=session_id, app_scope=app_scope)
    _remember(session)
    # Release surplus recordings first, so this session's capture does not push the host past the
    # concurrent budget.
    _enforce_capture_budget()

    task = DesktopCaptureTask(session)
    task.start()
    _CAPTURE_TASKS[session_id] = task
    return session


def lookup_session(session_id: str) -> RecordingSessionState | None:
    """Resolve a session and mark it as seen, so an active recording is not treated as idle."""
    session = _SESSIONS.get(session_id)
    if session is not None:
        session.touch()
    return session


async def stop_session(session_id: str) -> RecordingSessionState | None:
    """Stop a session's capture loop and mark it finalized."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return None
    session.touch()

    capture_task = _CAPTURE_TASKS.pop(session_id, None)
    if capture_task is not None:
        await capture_task.stop()

    session.status = "stopped"
    session.stopped_at = time.time()
    logger.info(
        "Stopped desktop skill recording session %s with %d events",
        session.session_id,
        len(session.events),
    )
    return session


def reset() -> None:
    """Drop all tracked sessions and cancel their capture loops (test/diagnostic helper)."""
    for task in _CAPTURE_TASKS.values():
        task.abandon()
    _CAPTURE_TASKS.clear()
    _SESSIONS.clear()


def _remember(session: RecordingSessionState) -> None:
    """Track a session, evicting the oldest finalized entries when the cap is exceeded."""
    # Re-insertion keeps dict order aligned with recency for the eviction scan below.
    _SESSIONS.pop(session.session_id, None)
    _SESSIONS[session.session_id] = session
    if len(_SESSIONS) <= _MAX_RETAINED_SESSIONS:
        return
    overflow = len(_SESSIONS) - _MAX_RETAINED_SESSIONS
    for sid in list(_SESSIONS):
        if overflow <= 0:
            break
        if _SESSIONS[sid].status != "recording":
            _SESSIONS.pop(sid, None)
            overflow -= 1


def _enforce_capture_budget() -> None:
    """Stop recordings beyond the concurrent-capture cap, oldest first.

    Each active session runs a native AX poll loop, so an unbounded number of them would pin the
    host. Finalized sessions are exempt because they no longer capture.
    """
    active = [sid for sid, s in _SESSIONS.items() if s.status == "recording"]
    excess = len(active) - _MAX_CONCURRENT_CAPTURES
    if excess <= 0:
        return
    for sid in active[:excess]:
        session = _SESSIONS.get(sid)
        if session is None:
            continue
        session.status = "stopped"
        session.stopped_at = time.time()
        capture_task = _CAPTURE_TASKS.pop(sid, None)
        if capture_task is not None:
            capture_task.abandon()
        logger.warning("Stopped recording %s: concurrent capture budget exceeded", sid)
