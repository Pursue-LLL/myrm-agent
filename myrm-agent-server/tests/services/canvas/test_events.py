"""Tests for app.services.canvas._events.

Covers: sse_events registry, notify_canvas_change behavior.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.canvas._events import notify_canvas_change, sse_events


@pytest.fixture(autouse=True)
def _clean_sse_events() -> None:
    """Ensure sse_events is empty before/after each test."""
    sse_events.clear()
    yield  # type: ignore[misc]
    sse_events.clear()


class TestNotifyCanvasChange:
    def test_noop_when_no_listeners(self) -> None:
        notify_canvas_change("nonexistent-canvas")

    def test_sets_single_event(self) -> None:
        evt = asyncio.Event()
        sse_events["canvas-1"] = {evt}

        notify_canvas_change("canvas-1")
        assert evt.is_set()

    def test_sets_multiple_events(self) -> None:
        evt1 = asyncio.Event()
        evt2 = asyncio.Event()
        sse_events["canvas-2"] = {evt1, evt2}

        notify_canvas_change("canvas-2")
        assert evt1.is_set()
        assert evt2.is_set()

    def test_only_targets_specified_canvas(self) -> None:
        evt_a = asyncio.Event()
        evt_b = asyncio.Event()
        sse_events["canvas-a"] = {evt_a}
        sse_events["canvas-b"] = {evt_b}

        notify_canvas_change("canvas-a")
        assert evt_a.is_set()
        assert not evt_b.is_set()

    def test_empty_bucket_is_noop(self) -> None:
        sse_events["canvas-empty"] = set()
        notify_canvas_change("canvas-empty")


class TestSseEventsRegistry:
    def test_registry_is_module_level_dict(self) -> None:
        assert isinstance(sse_events, dict)

    def test_registry_supports_add_remove(self) -> None:
        evt = asyncio.Event()
        sse_events.setdefault("test-canvas", set()).add(evt)
        assert evt in sse_events["test-canvas"]

        sse_events["test-canvas"].discard(evt)
        assert evt not in sse_events["test-canvas"]
