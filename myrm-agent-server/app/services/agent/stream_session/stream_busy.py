"""AgentBusy SSE responses for agent-stream."""

from __future__ import annotations

import uuid

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSEEnvelope, SSE_RESPONSE_HEADERS


def agent_busy_streaming_response(message_id: str | None) -> StreamingResponse:
    """Return the canonical AgentBusyError SSE envelope (HTTP 200 + error event)."""
    busy_event = {
        "type": "error",
        "error_type": "AgentBusyError",
        "data": "Agent is busy processing another request for this session.",
        "messageId": message_id or str(uuid.uuid4()),
        "status_code": 409,
    }
    chunk = SSEEnvelope.from_any(busy_event).to_sse_chunk()
    return StreamingResponse(
        iter([chunk]),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
