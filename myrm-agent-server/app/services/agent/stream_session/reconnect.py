"""SSE reconnect handling for agent streams."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.params import AgentRequest
from app.services.agent.streaming_support.sse_helpers import error_sse

logger = logging.getLogger(__name__)


async def try_stream_reconnect(request: AgentRequest, http_request: Request) -> StreamingResponse | None:
    """Return a reconnect StreamingResponse, or None if this is not a reconnect."""
    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

    last_event_id = http_request.headers.get("Last-Event-ID")
    if not (last_event_id and request.message_id):
        return None

    registry = GlobalStreamRegistry.get()
    if not await registry.has_buffer(request.message_id):
        logger.warning("Client reconnect failed: no active buffer for %s", request.message_id)
        return StreamingResponse(
            iter(
                [
                    error_sse(
                        "Session expired or server restarted. Please refresh.",
                        request.message_id,
                    )
                ]
            ),
            media_type="text/event-stream",
            headers=SSE_RESPONSE_HEADERS,
        )
    buffer = await registry.get_or_create(request.message_id)
    return StreamingResponse(
        buffer.subscribe(last_event_id),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
