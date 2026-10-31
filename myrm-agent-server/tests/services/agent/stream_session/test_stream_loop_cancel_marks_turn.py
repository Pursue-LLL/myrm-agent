"""A turn the user stopped is stored as stopped: the stream loop hands its cancel event to the collector that builds the stored row,
whether the stream still delivers a chunk after the Stop or ends without one."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
    iter_agent_stream_chunks,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

_CHAT_ID = "stopped-turn-chat"


def _message_chunk(text: str) -> str:
    return f"data: {json.dumps({'type': 'message', 'data': text, 'messageId': 'msg-1'})}\n\n"


def _session(cancel_token: CancellationToken, collector: StreamContentCollector) -> MagicMock:
    session = MagicMock()
    session.request.chat_id = _CHAT_ID
    session.request.action_mode = "general"
    session.request.use_workflow = False
    session.request.workflow_template_id = None
    session.request.workflow_template_args = None
    session.request.blueprint_id = None
    session.request.mention_references = None
    session.request.resume_value = None
    session.request.ephemeral_subagents = None
    session.routing_tier = "complex"
    session.params.message_id = "msg-1"
    session.cancel_token = cancel_token
    session.goal_provider = None
    session.collector = collector
    return session


def _message_end_chunk() -> str:
    return f"data: {json.dumps({'type': 'message_end', 'completion_status': 'complete', 'messageId': 'msg-1'})}\n\n"


async def _run_turn(
    token: CancellationToken,
    collector: StreamContentCollector,
    stream: Callable[..., AsyncIterator[str]],
) -> list[str]:
    try:
        with patch("app.services.agent.stream_session.stream_loop.ai_agent_service_stream", side_effect=stream):
            return [
                chunk
                async for chunk in iter_agent_stream_chunks(
                    _session(token, collector), ApprovalTimeoutHolder(), ClarificationTimeoutHolder()
                )
            ]
    finally:
        collector.cleanup()


def _assert_stored_as_stopped(collector: StreamContentCollector) -> None:
    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data.get("completionStatus") == "cancelled"
    stop_reason = extra_data.get("stopReason")
    assert isinstance(stop_reason, dict)
    assert stop_reason.get("code") == "agent_cancelled"
    assert stop_reason.get("message") == "Cancelled by user"


@pytest.mark.asyncio
async def test_stopped_turn_keeps_its_partial_reply_marked_cancelled() -> None:
    token = CancellationToken()
    collector = StreamContentCollector(chat_id=_CHAT_ID)

    async def stream_stopped_after_a_partial_reply(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _message_chunk("Partial reply")
        token.cancel(CancelReason.USER_CANCELLED)
        yield _message_chunk(" that is never kept")

    chunks = await _run_turn(token, collector, stream_stopped_after_a_partial_reply)

    assert any('"agent_cancelled"' in chunk for chunk in chunks)
    assert collector.content == "Partial reply"
    _assert_stored_as_stopped(collector)


@pytest.mark.asyncio
async def test_turn_whose_stream_ends_after_the_stop_without_another_chunk_is_marked_cancelled() -> None:
    token = CancellationToken()
    collector = StreamContentCollector(chat_id=_CHAT_ID)

    async def stream_that_ends_at_the_stop(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _message_chunk("Partial reply")
        token.cancel(CancelReason.USER_CANCELLED)

    chunks = await _run_turn(token, collector, stream_that_ends_at_the_stop)

    assert any('"agent_cancelled"' in chunk for chunk in chunks)
    assert collector.content == "Partial reply"
    _assert_stored_as_stopped(collector)


@pytest.mark.asyncio
async def test_turn_that_finished_before_the_stop_stays_complete() -> None:
    token = CancellationToken()
    collector = StreamContentCollector(chat_id=_CHAT_ID)

    async def stream_finished_then_stopped(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _message_chunk("Whole reply")
        yield _message_end_chunk()
        token.cancel(CancelReason.USER_CANCELLED)

    chunks = await _run_turn(token, collector, stream_finished_then_stopped)

    assert not any('"agent_cancelled"' in chunk for chunk in chunks)
    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data.get("completionStatus") == "complete"
    assert "stopReason" not in extra_data
