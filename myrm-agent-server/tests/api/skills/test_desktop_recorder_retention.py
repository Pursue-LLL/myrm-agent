"""Tests for recording-session retention in the desktop recorder API."""

from __future__ import annotations

from app.api.skills import desktop_recorder


def test_concurrent_capture_budget_stops_the_oldest() -> None:
    """Each active session runs a native poll loop, so the running set must stay bounded."""
    desktop_recorder._ACTIVE_SESSIONS.clear()
    desktop_recorder._CAPTURE_TASKS.clear()

    limit = desktop_recorder._MAX_CONCURRENT_CAPTURES
    sessions = []
    for index in range(limit + 1):
        session = desktop_recorder.RecordingSessionState(session_id=f"rec-{index}")
        desktop_recorder._remember_session(session)
        desktop_recorder._enforce_capture_budget()
        sessions.append(session)

    active = [s for s in sessions if s.status == "recording"]
    assert len(active) <= limit
    # The oldest recording is the one dropped; the newest must survive.
    assert sessions[0].status == "stopped"
    assert sessions[-1].status == "recording"

    desktop_recorder._ACTIVE_SESSIONS.clear()
    desktop_recorder._CAPTURE_TASKS.clear()


def test_finalized_sessions_are_evicted_past_the_retention_cap() -> None:
    """Abandoned recordings must not accumulate for the life of the process."""
    desktop_recorder._ACTIVE_SESSIONS.clear()
    desktop_recorder._CAPTURE_TASKS.clear()

    cap = desktop_recorder._MAX_RETAINED_SESSIONS
    for index in range(cap * 2):
        session = desktop_recorder.RecordingSessionState(session_id=f"rec-{index}")
        # Finalized sessions are the ones eligible for eviction.
        session.status = "stopped"
        desktop_recorder._remember_session(session)

    assert len(desktop_recorder._ACTIVE_SESSIONS) <= cap
    # The most recent session must survive, since a client may still publish right after stop.
    assert f"rec-{cap * 2 - 1}" in desktop_recorder._ACTIVE_SESSIONS

    desktop_recorder._ACTIVE_SESSIONS.clear()
    desktop_recorder._CAPTURE_TASKS.clear()


def test_active_recording_is_not_evicted() -> None:
    """A session that is still recording must never be dropped to make room."""
    desktop_recorder._ACTIVE_SESSIONS.clear()

    active = desktop_recorder.RecordingSessionState(session_id="rec-active")
    desktop_recorder._remember_session(active)

    cap = desktop_recorder._MAX_RETAINED_SESSIONS
    for index in range(cap * 2):
        finalized = desktop_recorder.RecordingSessionState(session_id=f"rec-done-{index}")
        finalized.status = "stopped"
        desktop_recorder._remember_session(finalized)

    assert "rec-active" in desktop_recorder._ACTIVE_SESSIONS

    desktop_recorder._ACTIVE_SESSIONS.clear()
