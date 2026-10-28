"""Stopping a run while the model request is still in flight, through the real agent chain.

A scripted chat model stays silent (a long prefill, hidden reasoning) or goes silent after a first chunk, inside a real
LangGraph agent driven by the production ``StreamExecutor`` with the production model-call cancel middleware. Stop only
flips the run's cancel token; the executor reads the token only when a stream chunk arrives, so the request itself must
be aborted and the turn must leave exactly as a Stop seen on a chunk does: cancelled, no error, no further request.

The silence lasts an hour, far beyond the settle window, so a run that ends in time was ended by the stop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from myrm_agent_harness.agent.middlewares.model_call_cancel import ModelCallCancelMiddleware
from myrm_agent_harness.agent.streaming.stream_compactor import StreamCompactor
from myrm_agent_harness.agent.streaming.stream_executor import STREAM_DONE, StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token

_SETTLE_S = 30.0
_SILENCE_S = 3600.0
_CUT_WITHIN_S = 3.0


class _Probe:
    """What the model request did: that it started, and whether the stop cancelled it under the model."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False
        self.requests = 0


class _FakeCompactor:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def put(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass

    def types(self) -> list[str]:
        kinds: list[str] = []
        for event in self.events:
            raw = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
            kinds.append(str(getattr(raw, "value", raw)))
        return kinds


def _model(
    probe: _Probe, *, silence_s: float, first_chunk: bool = False, error: Exception | None = None
) -> BaseChatModel:
    """A chat model that answers after ``silence_s`` seconds without ever looking at the stop."""

    class _SilentModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "scripted-silent"

        def bind_tools(self, tools: object, **kwargs: object) -> _SilentModel:
            return self

        def _generate(
            self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any
        ) -> ChatResult:
            raise NotImplementedError

        async def _wait(self) -> None:
            probe.requests += 1
            try:
                await asyncio.sleep(silence_s)
            except asyncio.CancelledError:
                probe.cancelled = True
                raise
            if error is not None:
                raise error

        async def _agenerate(
            self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any
        ) -> ChatResult:
            probe.started.set()
            await self._wait()
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="answer"))])

        async def _astream(
            self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any
        ) -> AsyncIterator[ChatGenerationChunk]:
            if first_chunk:
                yield ChatGenerationChunk(message=AIMessageChunk(content="partial "))
            probe.started.set()
            await self._wait()
            yield ChatGenerationChunk(message=AIMessageChunk(content="answer"))

    return _SilentModel()


@pytest.fixture(autouse=True)
def _clean_run_state() -> Iterator[None]:
    yield
    set_cancel_token(None)


def _run(model: BaseChatModel, token: CancellationToken) -> tuple[StreamExecutor, _FakeCompactor, AgentRunStatistics]:
    agent = create_agent(model, tools=[], middleware=[ModelCallCancelMiddleware()])
    stats = AgentRunStatistics()
    compactor = _FakeCompactor()
    context = {
        "locale": "en",
        "session_id": "e2e-stop-model",
        "workspace_path": "/tmp",
        "workspaces_storage_root": "/tmp",
    }
    ctx = StreamContext(
        agent=agent,
        agent_input={
            "messages": [
                HumanMessage(content="earlier question"),
                AIMessage(content="earlier answer"),
                HumanMessage(content="ask it"),
            ]
        },
        merged_context=context,
        run_config={"configurable": {"context": context, "thread_id": "e2e-stop-model"}},
        stats=stats,
        message_id="e2e_stop_model",
        cancel_token=token,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )
    executor = StreamExecutor(ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock())
    executor._compactor = cast(StreamCompactor, compactor)
    return executor, compactor, stats


async def _stop_when_started(probe: _Probe, token: CancellationToken, executing: asyncio.Task[None]) -> float:
    await asyncio.wait_for(probe.started.wait(), timeout=_SETTLE_S)
    stopped_at = time.monotonic()
    token.cancel(CancelReason.USER_CANCELLED)
    await asyncio.wait_for(executing, timeout=_SETTLE_S)
    return time.monotonic() - stopped_at


@pytest.mark.asyncio
async def test_stop_cuts_a_silent_model_request_and_the_run_ends_as_cancelled() -> None:
    token = CancellationToken("e2e_stop_model_silent")
    probe = _Probe()
    executor, compactor, stats = _run(_model(probe, silence_s=_SILENCE_S), token)
    set_cancel_token(token)  # as the agent runtime does before it spawns the executor task
    executing = asyncio.create_task(executor.execute())

    ended_after = await _stop_when_started(probe, token, executing)

    assert ended_after < _CUT_WITHIN_S
    assert probe.cancelled, "the request the stop interrupted must not keep running behind the ended run"
    assert stats.was_cancelled
    assert not stats.error_message
    assert compactor.types().count("cancelled") == 1
    assert "error" not in compactor.types()
    assert compactor.events[-1] is STREAM_DONE
    assert probe.requests == 1, "no further model request may follow the stop"


@pytest.mark.asyncio
async def test_stop_in_a_stream_gone_silent_after_a_chunk_reports_one_cancellation() -> None:
    token = CancellationToken("e2e_stop_model_stream")
    probe = _Probe()
    executor, compactor, stats = _run(_model(probe, silence_s=_SILENCE_S, first_chunk=True), token)
    set_cancel_token(token)
    executing = asyncio.create_task(executor.execute())

    ended_after = await _stop_when_started(probe, token, executing)

    assert ended_after < _CUT_WITHIN_S
    assert stats.was_cancelled
    assert not stats.error_message
    assert compactor.types().count("cancelled") == 1
    assert compactor.events[-1] is STREAM_DONE
    assert probe.requests == 1


@pytest.mark.asyncio
async def test_a_stop_set_before_the_request_never_reaches_the_model() -> None:
    token = CancellationToken("e2e_stop_model_before")
    token.cancel(CancelReason.USER_CANCELLED)
    probe = _Probe()
    executor, compactor, stats = _run(_model(probe, silence_s=_SILENCE_S), token)
    set_cancel_token(token)

    await asyncio.wait_for(executor.execute(), timeout=_SETTLE_S)

    assert probe.requests == 0
    assert stats.was_cancelled
    assert compactor.types().count("cancelled") == 1
    assert compactor.events[-1] is STREAM_DONE


@pytest.mark.asyncio
async def test_a_real_model_error_still_fails_the_run_instead_of_reading_as_a_stop() -> None:
    """The cut must not swallow genuine provider failures: they keep their error path (and so failover and retry)."""
    token = CancellationToken("e2e_model_error")
    probe = _Probe()
    executor, compactor, stats = _run(_model(probe, silence_s=0.01, error=RuntimeError("provider exploded")), token)
    set_cancel_token(token)

    with pytest.raises(MyrmLLMError):
        await asyncio.wait_for(executor.execute(), timeout=_SETTLE_S)

    assert not stats.was_cancelled
    assert (stats.error_message or "").startswith("RuntimeError")
    assert "error" in compactor.types()
    assert "cancelled" not in compactor.types()


@pytest.mark.asyncio
async def test_a_run_nobody_stops_gets_the_answer_of_the_same_model() -> None:
    """Control: without a stop the request completes, so the stop above is what ended the first run."""
    token = CancellationToken("e2e_no_stop_model")
    probe = _Probe()
    executor, compactor, stats = _run(_model(probe, silence_s=0.3), token)
    set_cancel_token(token)

    await asyncio.wait_for(executor.execute(), timeout=_SETTLE_S)

    assert not stats.was_cancelled
    assert "cancelled" not in compactor.types()
    answers = [event for event in compactor.events if getattr(event, "type", None) == "message"]
    assert answers, "the answer of the uninterrupted request must be streamed to the consumer"
