"""Recording session lifecycle manager.

Maintains in-memory recording sessions and coordinates between WebSocket
connections and the Harness ActionCaptureEngine. Sessions are ephemeral —
they only live while the recording is active. Stopped sessions are auto-pruned
after a configurable TTL to prevent memory leaks.


[INPUT]
- myrm_agent_harness.toolkits.browser.action_capture (POS: capture types and serializers)

[OUTPUT]
- register_session, get_session, remove_session: session lifecycle
- list_active_sessions: active session listing
- get_session_export: full session data for skill generation
- step_to_dict: single step serialization

[POS]
In-memory session store for browser recording. Auto-prunes stopped sessions
older than 30 minutes on each register call to prevent unbounded growth.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.action_capture import (
    CaptureSession,
    serialize_session,
    serialize_step,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.action_capture import ActionStep

logger = logging.getLogger(__name__)

_sessions: dict[str, CaptureSession] = {}
_SESSION_TTL_SECONDS = 1800  # 30 minutes


def _prune_stale_sessions() -> None:
    """Remove stopped sessions older than TTL to prevent memory leaks."""
    now = time.time()
    stale = [
        sid
        for sid, s in _sessions.items()
        if s.status == "stopped" and (now - s.start_time) > _SESSION_TTL_SECONDS
    ]
    for sid in stale:
        _sessions.pop(sid, None)
        logger.debug(f"Auto-pruned stale session: {sid}")


def register_session(session: CaptureSession) -> None:
    """Register a capture session for tracking."""
    _prune_stale_sessions()
    _sessions[session.session_id] = session
    logger.info(f"Recording session registered: {session.session_id}")


def get_session(session_id: str) -> CaptureSession | None:
    """Get a session by ID."""
    return _sessions.get(session_id)


def remove_session(session_id: str) -> CaptureSession | None:
    """Remove and return a session."""
    session = _sessions.pop(session_id, None)
    if session:
        logger.info(f"Recording session removed: {session_id}")
    return session


def list_active_sessions() -> list[dict[str, object]]:
    """List all active recording sessions (summary only)."""
    return [
        {
            "session_id": s.session_id,
            "status": s.status,
            "start_url": s.start_url,
            "step_count": len(s.steps),
        }
        for s in _sessions.values()
        if s.status != "stopped"
    ]


def get_session_export(session_id: str, *, include_screenshots: bool = False) -> dict[str, object] | None:
    """Get full session data for export/skill generation."""
    session = _sessions.get(session_id)
    if not session:
        return None
    return serialize_session(session, include_screenshots=include_screenshots)


def step_to_dict(step: ActionStep, *, include_screenshot: bool = True) -> dict[str, object]:
    """Convenience wrapper for serialize_step."""
    return serialize_step(step, include_screenshot=include_screenshot)
