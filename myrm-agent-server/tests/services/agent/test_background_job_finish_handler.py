"""Tests for ServerBackgroundJobFinishHandler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

from app.services.agent.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
    _format_finish_message,
)


def test_format_finish_message_success() -> None:
    msg = _format_finish_message(
        BackgroundJobFinishResult(
            session_id="chat-1",
            pid=42,
            command="npm run dev",
            status="exited",
            exit_code=0,
            error_category=None,
        )
    )
    assert "completed" in msg
    assert "42" in msg


@pytest.mark.asyncio
async def test_handler_appends_message_and_publishes_event() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-abc",
        pid=7,
        command="sleep 1",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    mock_bus = MagicMock()
    with (
        patch(
            "app.services.agent.background_job_finish_handler.ChatService.append_message",
            AsyncMock(),
        ) as mock_append,
        patch(
            "app.services.agent.background_job_finish_handler.get_event_bus",
            return_value=mock_bus,
        ),
    ):
        await handler._process(result)

    mock_append.assert_awaited_once()
    assert mock_append.await_args.kwargs["chat_id"] == "chat-abc"
    assert mock_append.await_args.kwargs["role"] == "assistant"
    mock_bus.publish.assert_called_once()
    published = mock_bus.publish.call_args[0][0]
    assert published.data["meta_data"]["kind"] == "background_job_finish"
    assert published.data["title"] == "Background task finished"


@pytest.mark.asyncio
async def test_handler_skips_non_exited_status() -> None:
    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-abc",
        pid=7,
        command="sleep 1",
        status="killed",
        exit_code=None,
        error_category=None,
    )

    with patch(
        "app.services.agent.background_job_finish_handler.ChatService.append_message",
        AsyncMock(),
    ) as mock_append:
        await handler.on_background_job_finish(result)
        await asyncio.sleep(0.05)

    mock_append.assert_not_called()
