"""Shared SSE status streaming for eval endpoints.

[INPUT]
- a status getter callable returning the current eval status dict.

[OUTPUT]
- stream_status_events: async generator emitting SSE frames for an eval
  status dict, deduplicating unchanged states and closing on is_running=false.

[POS]
HTTP-layer helper for the eval module. Reused by the single-profile eval,
matrix, and memory A/B status streams so the SSE framing contract lives in
one place.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Callable

StatusGetter = Callable[[], dict[str, object]]


async def stream_status_events(
    status_getter: StatusGetter,
    *,
    poll_interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Emit SSE frames for a polling status dict.

    Yields a ``data:`` frame only when the serialized status changed since
    the last poll (deduping), emits an ``event: close`` frame when
    ``is_running`` turns false, and ends the stream. Polls every
    ``poll_interval`` seconds.
    """
    last_state_str = ""
    while True:
        status_info = status_getter()
        current_state_str = json.dumps(status_info)
        if current_state_str != last_state_str:
            yield f"data: {current_state_str}\n\n"
            last_state_str = current_state_str

        if not status_info.get("is_running"):
            yield "event: close\ndata: {}\n\n"
            break

        await asyncio.sleep(poll_interval)
