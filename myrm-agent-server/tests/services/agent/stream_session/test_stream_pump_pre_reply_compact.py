"""Tests for pre-reply stale compact SSE emission in stream_pump."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_pump import pump_to_buffer
from app.services.chat.compact_service import CompactResult

_PUMP_STREAM_PATH = "app.services.agent.stream_session.stream_pump.generate_cancellable_stream"
_MUX_PATH = "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer"


async def _empty_stream():
    if False:
        yield ""


@pytest.mark.asyncio
async def test_pump_emits_context_compaction_when_pre_reply_compact_succeeded() -> None:
    session = MagicMock()
    session.pre_reply_compact_result = CompactResult(
        compacted=True,
        tokens_saved=1500,
        backup_path=".myrm/chat_backups/chat-1/20260101.jsonl",
        attempted=True,
    )
    session.pre_reply_compact_sse_sent = False
    session.params.message_id = "msg-1"
    session.params.project_id = None
    session.request.chat_id = "chat-1"
    session.is_long_running_task = False
    session.durable_registered = False
    session.had_fatal_error = False
    session.collector = MagicMock()
    session.registry.remove = AsyncMock()

    buffer = MagicMock()
    buffer.append = AsyncMock()
    buffer.end_stream = AsyncMock()

    with (
        patch(_PUMP_STREAM_PATH, return_value=_empty_stream()),
        patch(_MUX_PATH) as mock_mux,
    ):
        mock_mux.get.return_value.publish = AsyncMock()
        await pump_to_buffer(session, buffer)

    first_chunk = buffer.append.await_args_list[0].args[0]
    assert "context_compaction" in first_chunk
    assert "completed" in first_chunk
    assert "1500" in first_chunk


@pytest.mark.asyncio
async def test_pump_skips_context_compaction_when_pre_reply_compact_skipped() -> None:
    session = MagicMock()
    session.pre_reply_compact_result = CompactResult(compacted=False, reason="idle_compact_disabled")
    session.pre_reply_compact_sse_sent = False
    session.params.message_id = "msg-2"
    session.params.project_id = None
    session.request.chat_id = "chat-2"
    session.is_long_running_task = False
    session.durable_registered = False
    session.had_fatal_error = False
    session.collector = MagicMock()
    session.registry.remove = AsyncMock()

    buffer = MagicMock()
    buffer.append = AsyncMock()
    buffer.end_stream = AsyncMock()

    with (
        patch(_PUMP_STREAM_PATH, return_value=_empty_stream()),
        patch(_MUX_PATH) as mock_mux,
    ):
        mock_mux.get.return_value.publish = AsyncMock()
        await pump_to_buffer(session, buffer)

    for call in buffer.append.await_args_list:
        chunk = call.args[0]
        assert "context_compaction" not in chunk


@pytest.mark.asyncio
async def test_pump_skips_duplicate_sse_when_already_sent() -> None:
    session = MagicMock()
    session.pre_reply_compact_result = CompactResult(
        compacted=True,
        tokens_saved=1500,
        attempted=True,
    )
    session.pre_reply_compact_sse_sent = True
    session.params.message_id = "msg-3"
    session.params.project_id = None
    session.request.chat_id = "chat-3"
    session.is_long_running_task = False
    session.durable_registered = False
    session.had_fatal_error = False
    session.collector = MagicMock()
    session.registry.remove = AsyncMock()

    buffer = MagicMock()
    buffer.append = AsyncMock()
    buffer.end_stream = AsyncMock()

    with (
        patch(_PUMP_STREAM_PATH, return_value=_empty_stream()),
        patch(_MUX_PATH) as mock_mux,
    ):
        mock_mux.get.return_value.publish = AsyncMock()
        await pump_to_buffer(session, buffer)

    for call in buffer.append.await_args_list:
        chunk = call.args[0]
        assert "context_compaction" not in chunk
