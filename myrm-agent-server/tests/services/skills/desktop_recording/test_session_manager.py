"""Tests for desktop recording session registry: retention and capture budget."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.skills.desktop_recording import (
    create_session,
    lookup_session,
    reset,
    session_count,
    session_manager,
    stop_session,
)


@pytest.fixture(autouse=True)
def _isolated_registry_without_capture():
    """Isolate each test and never start a native capture loop from a unit test."""
    reset()
    with patch.object(session_manager.DesktopCaptureTask, "start", return_value=None):
        yield
    reset()


def test_concurrent_capture_budget_stops_the_oldest() -> None:
    """Each active session runs a native poll loop, so the running set must stay bounded."""
    limit = session_manager._MAX_CONCURRENT_CAPTURES
    sessions = [create_session(f"rec-{i}", "all") for i in range(limit + 1)]

    active = [s for s in sessions if s.status == "recording"]
    assert len(active) <= limit
    # The oldest recording is the one released; the newest must survive.
    assert sessions[0].status == "stopped"
    assert sessions[-1].status == "recording"


def test_finalized_sessions_are_evicted_past_the_retention_cap() -> None:
    """Abandoned recordings must not accumulate for the life of the process."""
    cap = session_manager._MAX_RETAINED_SESSIONS
    count = cap * 2
    for index in range(count):
        create_session(f"rec-{index}", "all")
        # Finalized sessions are the ones eligible for eviction.
        session_manager._SESSIONS[f"rec-{index}"].status = "stopped"

    assert session_count() <= cap
    # The most recent session survives: a client may still publish right after stopping.
    assert lookup_session(f"rec-{count - 1}") is not None


def test_active_recording_is_not_evicted() -> None:
    """A session that is still recording must never be dropped to make room."""
    session_manager._MAX_RETAINED_SESSIONS = 2
    create_session("rec-active", "all")

    for index in range(6):
        create_session(f"rec-done-{index}", "all")
        session_manager._SESSIONS[f"rec-done-{index}"].status = "stopped"

    # The registry must have kept the still-recording session even under pressure.
    session_manager._SESSIONS.pop("rec-done-5", None)  # evictable neighbours may be dropped
    assert lookup_session("rec-active") is not None


@pytest.mark.anyio
async def test_stop_session_finalizes_and_marks_stopped() -> None:
    """Stopping a recording must finalize it so retention can reclaim it."""
    create_session("rec-stop", "all")

    session = await stop_session("rec-stop")

    assert session is not None
    assert session.status == "stopped"
    assert session.stopped_at is not None


def test_lookup_marks_session_seen() -> None:
    """Polling must refresh the idle clock, or an active recording would be reaped."""
    session = create_session("rec-seen", "all")
    session.last_seen_at = 0.0

    lookup_session("rec-seen")

    assert session.last_seen_at > 0.0


def test_lookup_unknown_session_returns_none() -> None:
    """An unknown id is not an error here; the API layer maps it to 404."""
    assert lookup_session("missing") is None
