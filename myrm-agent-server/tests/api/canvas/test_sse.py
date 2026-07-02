"""Tests for canvas SSE multi-connection support.

Verifies that _sse_events uses set-based storage so multiple connections
to the same canvas_id all receive notifications independently.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.canvas._events import notify_canvas_change, sse_events


@pytest.fixture(autouse=True)
def _clear_sse_events() -> None:
    """Ensure clean SSE state between tests."""
    sse_events.clear()
    yield  # type: ignore[misc]
    sse_events.clear()


CANVAS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestSSEMultiConnection:
    def test_multiple_events_stored_in_set(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        assert len(sse_events[CANVAS_ID]) == 2

    def test_notify_triggers_all_events(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        notify_canvas_change(CANVAS_ID)

        assert event_a.is_set()
        assert event_b.is_set()

    def test_notify_noop_for_unknown_canvas(self) -> None:
        notify_canvas_change("00000000-0000-0000-0000-000000000000")

    def test_discard_removes_only_own_event(self) -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()
        sse_events.setdefault(CANVAS_ID, set()).add(event_a)
        sse_events.setdefault(CANVAS_ID, set()).add(event_b)

        bucket = sse_events.get(CANVAS_ID)
        assert bucket is not None
        bucket.discard(event_a)

        assert len(sse_events[CANVAS_ID]) == 1
        assert event_b in sse_events[CANVAS_ID]

    def test_empty_bucket_cleanup(self) -> None:
        event_a = asyncio.Event()
        sse_events.setdefault(CANVAS_ID, set()).add(event_a)

        bucket = sse_events.get(CANVAS_ID)
        assert bucket is not None
        bucket.discard(event_a)
        if not bucket:
            sse_events.pop(CANVAS_ID, None)

        assert CANVAS_ID not in sse_events
