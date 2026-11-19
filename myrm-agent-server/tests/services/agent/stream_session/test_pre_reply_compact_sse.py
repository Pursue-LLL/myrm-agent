"""Tests for pre-reply idle compact Web SSE lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.stream_session.pre_reply_compact_sse import run_pre_reply_compact_with_sse
from app.services.chat.compact_service import CompactResult


async def _run_with_gate(buffer: AsyncMock, gate_result: CompactResult, *, announces_active: bool = True) -> None:
    """Run the SSE lifecycle against a gate that returns ``gate_result``."""

    async def _fake_gate(*_args: object, **kwargs: object) -> CompactResult:
        on_active = kwargs.get("on_before_compact")
        if announces_active and on_active is not None:
            await on_active()
        return gate_result

    with patch(
        "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
        AsyncMock(side_effect=_fake_gate),
    ) as mock_gate:
        await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )
    mock_gate.assert_awaited_once()
    assert mock_gate.await_args.kwargs["on_before_compact"] is not None


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_active_and_completed() -> None:
    buffer = AsyncMock()

    await _run_with_gate(
        buffer,
        CompactResult(compacted=True, tokens_saved=900, backup_path="/tmp/backup.jsonl", attempted=True),
    )

    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert len(chunks) == 2, "active, then the outcome exactly once"
    assert "active" in chunks[0]
    assert "completed" in chunks[1]
    assert "900" in chunks[1]


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_failure_when_attempted() -> None:
    buffer = AsyncMock()

    await _run_with_gate(
        buffer,
        CompactResult(compacted=False, reason="timeout: summarize exceeded budget", attempted=True),
    )

    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert len(chunks) == 2, "active, then the outcome exactly once"
    assert "active" in chunks[0]
    assert "timeout" in chunks[1]


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_emits_failure_on_gate_exception() -> None:
    buffer = AsyncMock()

    with patch(
        "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
        AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        await run_pre_reply_compact_with_sse(
            buffer,
            chat_id="chat-1",
            message_id="msg-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    chunks = [call.args[0] for call in buffer.append.await_args_list]
    assert len(chunks) == 1, "the gate raised before announcing anything, so only the failure is sent"
    assert "failed" in chunks[0]


@pytest.mark.asyncio
async def test_run_pre_reply_compact_with_sse_stays_silent_when_the_gate_did_not_attempt() -> None:
    buffer = AsyncMock()

    await _run_with_gate(
        buffer,
        CompactResult(compacted=False, reason="idle_compact_disabled"),
        announces_active=False,
    )

    buffer.append.assert_not_called()
