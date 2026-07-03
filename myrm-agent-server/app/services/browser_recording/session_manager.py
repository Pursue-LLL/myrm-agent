"""Recording session lifecycle manager.

Maintains in-memory recording sessions and coordinates between WebSocket
connections and the Harness ActionCaptureEngine. Sessions are ephemeral —
they only live while the recording is active (no persistence needed).
"""

from __future__ import annotations

import logging
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


def register_session(session: CaptureSession) -> None:
    """Register a capture session for tracking."""
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
