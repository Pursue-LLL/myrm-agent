"""Tests for pre-reply idle compact Web SSE lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.compact_service import CompactResult
from app.services.agent.stream_session.pre_reply_compact_sse import (
    append_pre_reply_compact_sse,
    run_pre_reply_compact_with_sse,
)


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_active_and_completed() -> None:
    buffer = AsyncMock()
    gate_result = CompactResult(
        compacted=True,
        tokens_saved=900,
        backup_path="/tmp/backup.jsonl",
        attempted=True,
    )

    async def _fake_gate(*_args, **kwargs):
        on_active = kwargs.get("on_before_compact")
        if on_active is not None:
            await on_active()
        return gate_result

    with patch(
        "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
        AsyncMock(side_effect=_fake_gate),
    ) as mock_gate:
        result = await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    assert result is gate_result
    mock_gate.assert_awaited_once()
    assert mock_gate.await_args.kwargs["on_before_compact"] is not None
    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert any("active" in chunk for chunk in chunks)
    assert any("completed" in chunk for chunk in chunks)
    assert any("900" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_failure_when_attempted() -> None:
    buffer = AsyncMock()
    gate_result = CompactResult(
        compacted=False,
        reason="timeout: summarize exceeded budget",
        attempted=True,
    )

    async def _fake_gate(*_args, **kwargs):
        on_active = kwargs.get("on_before_compact")
        if on_active is not None:
            await on_active()
        return gate_result

    with patch(
        "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
        AsyncMock(side_effect=_fake_gate),
    ):
        result = await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    assert result is gate_result
    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert any("active" in chunk for chunk in chunks)
    assert any("timeout" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_failure_on_gate_exception() -> None:
    buffer = AsyncMock()

    with patch(
        "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
        AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        result = await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    assert result is not None
    assert result.attempted is True
    assert result.reason is not None
    assert "gate_failed" in result.reason
    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert any("failed" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_append_pre_reply_compact_sse_skips_idle_disabled() -> None:
    buffer = AsyncMock()
    await append_pre_reply_compact_sse(
        buffer,
        "msg-1",
        CompactResult(compacted=False, reason="idle_compact_disabled"),
    )
    buffer.append.assert_not_called()
