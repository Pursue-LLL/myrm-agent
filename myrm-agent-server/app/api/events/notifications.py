"""SSE endpoint for real-time system notifications.

Clients connect to GET /events/notifications/stream and receive
newline-delimited JSON events. A heartbeat is sent every 30 s to
keep the connection alive through proxies.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.event.app_event_bus import AppEvent, get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications")

_HEARTBEAT_INTERVAL = 30  # seconds


async def _sse_generator(request: Request) -> AsyncIterator[str]:
    """Yield SSE-formatted lines until the client disconnects."""
    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event: AppEvent = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_INTERVAL)
                payload = json.dumps(
                    {"type": event.event_type, "data": event.data, "timestamp": event.timestamp},
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        bus.unsubscribe(queue)


@router.get("/stream")
async def notification_stream(request: Request) -> StreamingResponse:
    """SSE stream for real-time system notifications (pairing requests, etc.)."""
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
