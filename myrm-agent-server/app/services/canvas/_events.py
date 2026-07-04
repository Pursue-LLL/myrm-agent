"""Canvas SSE event notification hub.

[INPUT]
(none — leaf utility)

[OUTPUT]
- sse_events: module-level SSE event registry
- pending_hints: module-level hint queue for SSE consumers
- notify_canvas_change: trigger SSE for a canvas
- notify_batch_layout_done: trigger SSE with zoom-to-fit hint

[POS]
Centralises SSE event management for canvas changes so both the REST API
router (api layer) and agent tools (services layer) can trigger
notifications without introducing a reverse dependency.
"""

from __future__ import annotations

import asyncio
from collections import deque

sse_events: dict[str, set[asyncio.Event]] = {}
"""canvas_id → set of asyncio.Event objects for active SSE connections."""

pending_hints: dict[str, deque[str]] = {}
"""canvas_id → bounded queue of SSE event hints (e.g. "batch-layout-done")."""


def notify_canvas_change(canvas_id: str) -> None:
    """Signal all SSE listeners that a canvas has changed."""
    bucket = sse_events.get(canvas_id)
    if bucket:
        for event in bucket:
            event.set()


_MAX_PENDING_HINTS = 16


def notify_batch_layout_done(canvas_id: str) -> None:
    """Signal SSE listeners with a batch-layout-done hint (triggers zoomToFit)."""
    q = pending_hints.setdefault(canvas_id, deque(maxlen=_MAX_PENDING_HINTS))
    q.append("batch-layout-done")
    notify_canvas_change(canvas_id)


def consume_hint(canvas_id: str) -> str | None:
    """Pop and return the next pending hint for this canvas, or None."""
    queue = pending_hints.get(canvas_id)
    if queue:
        return queue.popleft()
    return None
