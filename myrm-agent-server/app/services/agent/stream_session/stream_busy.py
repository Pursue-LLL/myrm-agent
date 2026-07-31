"""AgentBusy SSE responses for agent-stream.

[INPUT]
- app.schemas.streaming::SSEEnvelope (POS: canonical SSE chunk encoding)

[OUTPUT]
- agent_busy_streaming_response: HTTP 200 SSE with AgentBusyError envelope

[POS]
Shared stream-session response for concurrent agent-stream requests on the same chat.
"""

from __future__ import annotations

import uuid

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope


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
