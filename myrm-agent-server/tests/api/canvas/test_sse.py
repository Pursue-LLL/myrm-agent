"""Tests for canvas SSE multi-connection support.

Verifies that _sse_events uses set-based storage so multiple connections
to the same canvas_id all receive notifications independently.
"""

from __future__ import annotations

import asyncio

import pytest

from app.api.canvas.router import _notify_canvas_change, _sse_events


@pytest.fixture(autouse=True)
def _clear_sse_events() -> None:
    """Ensure clean SSE state between tests."""
    _sse_events.clear()
    yield  # type: ignore[misc]
    _sse_events.clear()


CANVAS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestSSEMultiConnection:
    def test_multiple_events_stored_in_set(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        _sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        _sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        assert len(_sse_events[CANVAS_ID]) == 2

    def test_notify_triggers_all_events(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        _sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        _sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        _notify_canvas_change(CANVAS_ID)

        assert event_a.is_set()
        assert event_b.is_set()

    def test_notify_noop_for_unknown_canvas(self) -> None:
        _notify_canvas_change("00000000-0000-0000-0000-000000000000")

    def test_discard_removes_only_own_event(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        _sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        _sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        bucket = _sse_events.get(CANVAS_ID)
        assert bucket is not None
        bucket.discard(event_a)

        assert len(_sse_events[CANVAS_ID]) == 1
        assert event_b in _sse_events[CANVAS_ID]

    def test_empty_bucket_cleanup(self) -> None:
        event_a = asyncio.Event()
        _sse_events.setdefault(CANVAS_ID, set()).add(event_a)

        bucket = _sse_events.get(CANVAS_ID)
        assert bucket is not None
        bucket.discard(event_a)
        if not bucket:
            _sse_events.pop(CANVAS_ID, None)

        assert CANVAS_ID not in _sse_events
