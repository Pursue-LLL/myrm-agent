"""generate_cancellable_stream owns the disconnect watch and ends it before finalize on every exit path."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session import stream_chunks
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from tests.api.agent.utils import get_model_selection


def _session() -> AgentStreamSession:
    return AgentStreamSession(
        request=AgentRequest(
            message_id="msg-watch",
            chat_id="chat-watch",
            query="hello",
            model_selection=get_model_selection(),
        ),
        http_request=cast(Request, None),
        params=GeneralAgentParams(
            message_id="msg-watch",
            chat_id="chat-watch",
            query="hello",
            model_cfg=ModelConfig(model="claude-3-7-sonnet", api_key="sk-test"),
        ),
        cancel_token=CancellationToken(request_id="msg-watch"),
        steering_token=None,
        routing_tier=None,
        archive_restore_results=[],
        research_model_cfg=None,
        registry=None,
        collector=StreamContentCollector(chat_id="chat-watch"),
        is_long_running_task=False,
        goal_provider=None,
        extra_context={},
    )


async def _drive_generator(
    timeline: list[str],
    *,
    stream_error: BaseException | None = None,
    abandon_after_first_chunk: bool = False,
) -> None:
    @asynccontextmanager
    async def recording_watch(_session: AgentStreamSession) -> AsyncIterator[None]:
        timeline.append("watch:enter")
        try:
            yield
        finally:
            timeline.append("watch:exit")

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        timeline.append("stream")
        yield "chunk-1"
        if stream_error is not None:
            raise stream_error
        yield "chunk-2"

    async def fake_exception_chunks(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        timeline.append("exception-handler")
        for chunk in ():
            yield chunk

    async def fake_finalize(*_args: object, **_kwargs: object) -> None:
        timeline.append("finalize")

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.agent.stream_session.migration_readiness_preflight.resolve_and_build_migration_readiness_gap_sse_event",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch.object(stream_chunks, "watch_client_disconnect", recording_watch),
        patch.object(stream_chunks, "iter_agent_stream_chunks", fake_stream),
        patch.object(stream_chunks, "yield_stream_exception_chunks", fake_exception_chunks),
        patch.object(stream_chunks, "finalize_agent_stream_session", fake_finalize),
    ):
        stream = stream_chunks.generate_cancellable_stream(_session())
        if abandon_after_first_chunk:
            async for chunk in stream:
                if chunk == "chunk-1":
                    break
            await stream.aclose()
        else:
            async for _chunk in stream:
                pass


@pytest.mark.asyncio
async def test_watch_ends_before_finalize_when_the_stream_completes() -> None:
    timeline: list[str] = []

    await _drive_generator(timeline)

    assert timeline == ["watch:enter", "stream", "watch:exit", "finalize"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_error", [RuntimeError("boom"), asyncio.CancelledError()])
async def test_watch_ends_before_finalize_when_the_stream_fails(stream_error: BaseException) -> None:
    timeline: list[str] = []

    await _drive_generator(timeline, stream_error=stream_error)

    assert timeline == ["watch:enter", "stream", "exception-handler", "watch:exit", "finalize"]


@pytest.mark.asyncio
async def test_watch_ends_before_finalize_when_the_consumer_abandons_the_stream() -> None:
    timeline: list[str] = []

    await _drive_generator(timeline, abandon_after_first_chunk=True)

    assert timeline == ["watch:enter", "stream", "exception-handler", "watch:exit", "finalize"]
