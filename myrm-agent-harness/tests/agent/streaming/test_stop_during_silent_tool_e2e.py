"""Stopping a run while a silent tool call is in flight, through the real agent chain.

A scripted model calls a tool that only waits for its result and never looks at the stop (the shape of a remote MCP or
web call), inside a real LangGraph agent driven by the production ``StreamExecutor`` with the production tool
interceptor. Stop only flips the run's cancel token, and that alone must cancel the call itself, end the run and keep
the model from being asked again: a call left running behind a stopped turn keeps its side effects and can write into
the next turn.

The assertions are about outcomes and ordering; the tool's own deadline (two minutes) is far beyond the settle window,
so a run that ends in time was ended by the stop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import tool_interceptor_middleware
from myrm_agent_harness.agent.streaming.stream_compactor import StreamCompactor
from myrm_agent_harness.agent.streaming.stream_executor import STREAM_DONE, StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until

_SETTLE_S = 30.0
_CALL_SECONDS = 3600.0


class _ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


class _FakeCompactor:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def put(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass


class _Probe:
    """What the silent tool did: that it started, and whether the call was cancelled under it."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False
        self.finished = False


@pytest.fixture(autouse=True)
def _clean_run_state() -> Iterator[None]:
    yield
    set_cancel_token(None)


def _run(
    probe: _Probe, seconds: float, token: CancellationToken
) -> tuple[StreamExecutor, _FakeCompactor, _ScriptedModel, AgentRunStatistics]:
    @tool
    async def mcp_silent_probe(reason: str) -> str:
        """A remote call that waits for its result and has no cancel hook."""
        probe.started.set()
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            probe.cancelled = True
            raise
        probe.finished = True
        return "remote result"

    model = _ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "mcp_silent_probe", "args": {"reason": "ask"}, "id": "call_1"}]),
            AIMessage(content="finished"),
        ]
    )
    agent = create_agent(model, tools=[mcp_silent_probe], middleware=[tool_interceptor_middleware])
    stats = AgentRunStatistics()
    compactor = _FakeCompactor()
    context = {
        "locale": "en",
        "session_id": "e2e-stop-silent",
        "workspace_path": "/tmp",
        "workspaces_storage_root": "/tmp",
    }
    ctx = StreamContext(
        agent=agent,
        agent_input={"messages": [HumanMessage(content="ask it")]},
        merged_context=context,
        run_config={"configurable": {"context": context, "thread_id": "e2e-stop-silent"}},
        stats=stats,
        message_id="e2e_stop_silent",
        cancel_token=token,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )
    executor = StreamExecutor(ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock())
    executor._compactor = cast(StreamCompactor, compactor)
    return executor, compactor, model, stats


@pytest.mark.asyncio
async def test_stop_cancels_a_silent_call_ends_the_run_and_the_model_is_not_asked_again() -> None:
    token = CancellationToken("e2e_stop_silent")
    probe = _Probe()
    executor, compactor, model, stats = _run(probe, _CALL_SECONDS, token)
    set_cancel_token(token)  # as the agent runtime does before it spawns the executor task
    executing = asyncio.create_task(executor.execute())
    await asyncio.wait_for(probe.started.wait(), timeout=_SETTLE_S)

    token.cancel(CancelReason.USER_CANCELLED)
    await asyncio.wait_for(executing, timeout=_SETTLE_S)

    assert probe.cancelled, "the call the stop interrupted must not keep running behind the ended run"
    assert not probe.finished
    assert stats.was_cancelled
    assert compactor.events[-1] is STREAM_DONE
    assert model.i == 1, "no further model request may follow the stop"


@pytest.mark.asyncio
async def test_a_run_nobody_stops_gets_the_result_of_the_same_call() -> None:
    """Control: without a stop the call completes and the model answers, so the stop above is what ended the first run."""
    token = CancellationToken("e2e_no_stop_silent")
    probe = _Probe()
    executor, compactor, _model, stats = _run(probe, 0.05, token)
    set_cancel_token(token)

    await asyncio.wait_for(executor.execute(), timeout=_SETTLE_S)
    await wait_until(lambda: probe.finished, 1.0)

    assert not stats.was_cancelled
    answers = [event for event in compactor.events if getattr(event, "type", None) == "message"]
    assert [getattr(event, "data", None) for event in answers] == ["finished"]
