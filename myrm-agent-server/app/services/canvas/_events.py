"""Canvas SSE event notification hub.

[INPUT]
(none — leaf utility)

[OUTPUT]
- sse_events: module-level SSE event registry
- notify_canvas_change: trigger SSE for a canvas

[POS]
Centralises SSE event management for canvas changes so both the REST API
router (api layer) and agent tools (services layer) can trigger
notifications without introducing a reverse dependency.
"""

from __future__ import annotations

import asyncio

sse_events: dict[str, set[asyncio.Event]] = {}
"""canvas_id → set of asyncio.Event objects for active SSE connections."""


def notify_canvas_change(canvas_id: str) -> None:
    """Signal all SSE listeners that a canvas has changed."""
    bucket = sse_events.get(canvas_id)
    if bucket:
        for event in bucket:
            event.set()
