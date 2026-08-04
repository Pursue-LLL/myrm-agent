"""E1 early buffered stream response shape tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.agent.stream_session.orchestrator_turn_body import (
    launch_early_buffered_stream,
)


@pytest.mark.asyncio
async def test_launch_early_buffered_stream_returns_sse_for_normal_web() -> None:
    request = MagicMock()
    request.message_id = "msg-1"
    request.multiplexed = False

    buffer = MagicMock()
    buffer.subscribe = MagicMock(return_value=iter(()))

    with patch(
        "app.services.agent.stream_session.orchestrator_turn_body.asyncio.create_task",
    ) as mock_create_task:
        mock_create_task.return_value = MagicMock(add_done_callback=MagicMock())
        response = await launch_early_buffered_stream(
            request=request,
            http_request=MagicMock(),
            text_content="hello",
            stream_started_at_monotonic=0.0,
            registry=MagicMock(),
            buffer=buffer,
            session_reservation=MagicMock(),
            record_terminal_failure=AsyncMock(),
        )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_launch_early_buffered_stream_returns_json_when_multiplexed() -> None:
    request = MagicMock()
    request.message_id = "msg-mux-1"
    request.multiplexed = True

    buffer = MagicMock()

    with patch(
        "app.services.agent.stream_session.orchestrator_turn_body.asyncio.create_task",
    ) as mock_create_task:
        mock_create_task.return_value = MagicMock(add_done_callback=MagicMock())
        response = await launch_early_buffered_stream(
            request=request,
            http_request=MagicMock(),
            text_content="hello",
            stream_started_at_monotonic=0.0,
            registry=MagicMock(),
            buffer=buffer,
            session_reservation=MagicMock(),
            record_terminal_failure=AsyncMock(),
        )

    assert isinstance(response, JSONResponse)
    assert response.body is not None
    payload = response.body.decode()
    assert '"status":"accepted"' in payload.replace(" ", "")
    assert "msg-mux-1" in payload
