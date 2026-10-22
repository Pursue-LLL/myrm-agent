"""An IM channel agent run counts as in flight while its stream is consumed, and always releases."""

from __future__ import annotations

import asyncio
import gc
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage
from app.core.agent.run_activity import active_background_agent_runs
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_EXECUTOR = "app.core.channel_bridge.agent_executor.executor"
_EVENTS: list[dict[str, object]] = [
    {"type": "message", "data": "one"},
    {"type": "message", "data": "two"},
    {"type": "message", "data": "three"},
]


class _FakeAgent:
    """Records the in-flight count seen from inside the agent run."""

    def __init__(self, *, fail_at: int | None = None) -> None:
        self.observed: list[int] = []
        self._fail_at = fail_at

    async def process_stream(self, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        for index, event in enumerate(_EVENTS):
            self.observed.append(active_background_agent_runs())
            if index == self._fail_at:
                raise RuntimeError("agent crashed")
            yield event


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Summarize my inbox",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": "en"},
    )


def _patched_executor(agent: _FakeAgent):
    prep = SimpleNamespace(
        agent=agent,
        token_ctx=None,
        chat_id="chat-1",
        chat_history=[],
        query_input="hi",
        channel_budget_key="",
        memory_settings=None,
        lite_model_cfg=None,
        session_was_auto_reset=False,
        session_policy=None,
        params=SimpleNamespace(agent_id="main"),
        agent_engine_params={},
        user_timezone="UTC",
    )
    return (
        patch(
            f"{_EXECUTOR}.prepare_channel_execution",
            AsyncMock(return_value=SimpleNamespace(pre_events=[], prep=prep)),
        ),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={})),
        patch(f"{_EXECUTOR}.finalize_channel_stream_reply", AsyncMock(return_value="reply")),
        patch(f"{_EXECUTOR}.finalize_agent_session", AsyncMock()),
    )


async def _settle() -> None:
    """Let the event loop finalize async generators that a consumer abandoned."""
    for _ in range(10):
        await asyncio.sleep(0)
        gc.collect()


@pytest.mark.asyncio
async def test_channel_run_counts_while_streaming_and_releases_on_completion() -> None:
    agent = _FakeAgent()
    baseline = active_background_agent_runs()
    prepare, runtime_context, reply, finalize = _patched_executor(agent)

    with prepare, runtime_context, reply, finalize:
        events = [event async for event in ChannelAgentExecutor().execute_stream(_inbound())]

    assert agent.observed == [baseline + 1] * len(_EVENTS)
    assert events[-1] == "reply"
    assert active_background_agent_runs() == baseline


@pytest.mark.asyncio
async def test_channel_run_is_released_when_the_agent_fails() -> None:
    agent = _FakeAgent(fail_at=1)
    baseline = active_background_agent_runs()
    prepare, runtime_context, reply, finalize = _patched_executor(agent)

    with prepare, runtime_context, reply, finalize:
        events = [event async for event in ChannelAgentExecutor().execute_stream(_inbound())]

    assert agent.observed == [baseline + 1, baseline + 1]
    assert events
    assert active_background_agent_runs() == baseline


@pytest.mark.asyncio
async def test_channel_run_is_released_when_the_consumer_stops_early() -> None:
    agent = _FakeAgent()
    baseline = active_background_agent_runs()
    prepare, runtime_context, reply, finalize = _patched_executor(agent)

    with prepare, runtime_context, reply, finalize:
        stream = ChannelAgentExecutor().execute_stream(_inbound())
        await anext(stream)
        assert active_background_agent_runs() == baseline + 1
        await stream.aclose()
        del stream
        await _settle()

    assert active_background_agent_runs() == baseline
