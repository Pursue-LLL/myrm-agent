"""A web turn hands the steering instructions its model never read back to the client, whichever way it ends."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session import stream_chunks
from app.services.agent.stream_session.steering_unread import STEERING_UNREAD_EVENT, unread_steering_chunk
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

_INSTRUCTION = "use postgres instead"


def _session(token: SteeringToken | None) -> AgentStreamSession:
    return AgentStreamSession(
        request=AgentRequest(message_id="msg-unread", chat_id="chat-unread", query="hello"),
        http_request=cast(Request, None),
        params=GeneralAgentParams(
            message_id="msg-unread",
            chat_id="chat-unread",
            query="hello",
            model_cfg=ModelConfig(model="claude-3-7-sonnet", api_key="sk-test"),
        ),
        cancel_token=CancellationToken(request_id="msg-unread"),
        steering_token=token,
        routing_tier=None,
        archive_restore_results=[],
        registry=cast(GlobalStreamRegistry, None),
        collector=StreamContentCollector(chat_id="chat-unread"),
        goal_provider=None,
        extra_context={},
    )


def _event(chunk: str) -> dict[str, object]:
    assert chunk.startswith("data: ")
    return json.loads(chunk.removeprefix("data: "))


async def _run(
    session: AgentStreamSession,
    timeline: list[str],
    *,
    accept_during_stream: str | None = None,
    read_during_stream: bool = False,
    stream_error: BaseException | None = None,
    abandon_after_first_chunk: bool = False,
) -> list[str]:
    token = session.steering_token

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        timeline.append("stream")
        yield "chunk-1"
        if token is not None and accept_during_stream is not None:
            assert token.steer(accept_during_stream) is True
        if token is not None and read_during_stream:
            token.collect_all_steering_messages()
        if stream_error is not None:
            raise stream_error
        yield "chunk-2"

    async def fake_exception_chunks(_session: AgentStreamSession, exc: BaseException) -> AsyncIterator[str]:
        timeline.append("exception-handler")
        if not isinstance(exc, GeneratorExit):
            yield "error-chunk"

    async def fake_finalize(*_args: object, **_kwargs: object) -> None:
        timeline.append("finalize")

    chunks: list[str] = []
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=None),
        patch(
            "app.services.agent.stream_session.migration_readiness_preflight.resolve_and_build_migration_readiness_gap_sse_event",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch.object(stream_chunks, "iter_agent_stream_chunks", fake_stream),
        patch.object(stream_chunks, "yield_stream_exception_chunks", fake_exception_chunks),
        patch.object(stream_chunks, "finalize_agent_stream_session", fake_finalize),
    ):
        stream = stream_chunks.generate_cancellable_stream(session)
        if abandon_after_first_chunk:
            async for chunk in stream:
                chunks.append(chunk)
                break
            await stream.aclose()
        else:
            chunks.extend([chunk async for chunk in stream])
    return chunks


@pytest.mark.asyncio
async def test_a_completed_turn_returns_the_instruction_it_never_read_before_it_finalizes() -> None:
    token = SteeringToken()
    timeline: list[str] = []

    chunks = await _run(_session(token), timeline, accept_during_stream=_INSTRUCTION)

    assert chunks[:2] == ["chunk-1", "chunk-2"]
    event = _event(chunks[2])
    assert event == {
        "type": STEERING_UNREAD_EVENT,
        "messageId": "msg-unread",
        "data": {"count": 1, "messages": [_INSTRUCTION]},
    }
    assert timeline == ["stream", "finalize"]
    assert token.steer("too late") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_error", [RuntimeError("boom"), asyncio.CancelledError()])
async def test_a_failed_turn_reports_its_error_first_and_then_returns_the_unread_instruction(
    stream_error: BaseException,
) -> None:
    token = SteeringToken()
    timeline: list[str] = []

    chunks = await _run(_session(token), timeline, accept_during_stream=_INSTRUCTION, stream_error=stream_error)

    assert chunks[:2] == ["chunk-1", "error-chunk"]
    assert _event(chunks[2])["data"] == {"count": 1, "messages": [_INSTRUCTION]}
    assert timeline == ["stream", "exception-handler", "finalize"]


@pytest.mark.asyncio
async def test_every_unread_instruction_comes_back_in_the_order_it_was_accepted() -> None:
    token = SteeringToken()
    token.steer("first")
    token.redirect("second")

    chunks = await _run(_session(token), [], accept_during_stream="third")

    assert _event(chunks[-1])["data"] == {"count": 3, "messages": ["first", "second", "third"]}


@pytest.mark.asyncio
async def test_a_turn_that_read_everything_it_accepted_returns_nothing() -> None:
    token = SteeringToken()

    chunks = await _run(_session(token), [], accept_during_stream=_INSTRUCTION, read_during_stream=True)

    assert chunks == ["chunk-1", "chunk-2"]


@pytest.mark.asyncio
async def test_a_cancelled_turn_ends_with_its_unread_instruction_and_sends_nothing() -> None:
    token = SteeringToken()
    session = _session(token)
    session.cancel_token.cancel()

    chunks = await _run(session, [], accept_during_stream=_INSTRUCTION)

    assert chunks == ["chunk-1", "chunk-2"]
    assert token.steer("too late") is False


@pytest.mark.asyncio
async def test_a_turn_without_a_steering_token_returns_nothing() -> None:
    chunks = await _run(_session(None), [])

    assert chunks == ["chunk-1", "chunk-2"]


@pytest.mark.asyncio
async def test_a_consumer_that_closed_the_stream_is_not_sent_anything_and_the_turn_still_finalizes() -> None:
    token = SteeringToken()
    token.steer(_INSTRUCTION)
    timeline: list[str] = []

    chunks = await _run(_session(token), timeline, abandon_after_first_chunk=True)

    assert chunks == ["chunk-1"]
    assert timeline == ["stream", "exception-handler", "finalize"]


def test_the_chunk_is_none_for_a_token_with_nothing_unread_and_closes_the_token() -> None:
    token = SteeringToken()

    assert unread_steering_chunk(_session(token)) is None
    assert token.steer("late") is False
