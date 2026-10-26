"""The real ChatLiteLLM adapter (stream and non-stream) driving the GenAI span lifecycle.

The provider client is the only fake; the adapter, its retry loop, the memo and the span
lifecycle are the production code.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import NoReturn

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import StatusCode

from myrm_agent_harness.infra.memo import LlmCallScope, MemoLedger, llm_call_scope
from myrm_agent_harness.infra.tracing.gen_ai import AgentRunSpan
from myrm_agent_harness.infra.tracing.gen_ai.content import CAPTURE_CONTENT_ENV
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import ChatLiteLLM

from .conftest import MemoryTelemetry

Json = dict[str, object]
ProviderReply = AsyncIterator[Json] | Json

CHAT = "chat gpt-4o-mini"
USAGE = {
    "prompt_tokens": 40,
    "completion_tokens": 8,
    "total_tokens": 48,
    "prompt_tokens_details": {"cached_tokens": 30},
}
CHUNKS: list[Json] = [
    {
        "id": "c1",
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello"}, "finish_reason": None}],
    },
    {"id": "c1", "model": "gpt-4o-mini-2024-07-18", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    {"id": "c1", "model": "gpt-4o-mini-2024-07-18", "choices": [], "usage": USAGE},
]
RESPONSE: Json = {
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": USAGE,
}


class FakeClient:
    """Provider client double: one scripted behaviour per call."""

    def __init__(self, *behaviours: Callable[[], ProviderReply]) -> None:
        self._behaviours = list(behaviours)
        self.calls = 0

    async def acreate(self, **kwargs: object) -> ProviderReply:
        behaviour = self._behaviours[min(self.calls, len(self._behaviours) - 1)]
        self.calls += 1
        return behaviour()


def _stream(chunks: list[Json] = CHUNKS) -> Callable[[], AsyncIterator[Json]]:
    async def gen() -> AsyncIterator[Json]:
        await asyncio.sleep(0.01)
        for chunk in chunks:
            yield chunk

    return gen


def _fail(exc: Exception) -> Callable[[], NoReturn]:
    def behaviour() -> NoReturn:
        raise exc

    return behaviour


def _model(client: FakeClient, *, streaming: bool) -> ChatLiteLLM:
    model = ChatLiteLLM(model="gpt-4o-mini", api_key="test-key")
    model.streaming = streaming
    model.client = client  # type: ignore[assignment]
    model.empty_retry_delay = 0.01
    return model


async def _drain(model: ChatLiteLLM, prompt: str = "hello") -> str:
    return "".join([str(chunk.content or "") async for chunk in model.astream(prompt)])


async def test_a_streaming_call_is_one_chat_span_with_ttft_and_usage(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_stream()), streaming=True)

    assert await _drain(model) == "hello"

    span = telemetry.span(CHAT)
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.request.stream"] is True
    assert attributes["gen_ai.provider.name"] == "openai"
    assert attributes["gen_ai.response.model"] == "gpt-4o-mini-2024-07-18"
    assert attributes["gen_ai.response.finish_reasons"] == ("stop",)
    assert attributes["gen_ai.usage.input_tokens"] == 40
    assert attributes["gen_ai.usage.output_tokens"] == 8
    assert attributes["gen_ai.usage.cache_read.input_tokens"] == 30
    assert attributes["gen_ai.response.time_to_first_chunk"] >= 0.01
    assert span.status.status_code is StatusCode.UNSET
    assert len(telemetry.metric_points("gen_ai.client.operation.duration")) == 1


async def test_a_non_streaming_call_is_one_chat_span_with_usage(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(lambda: RESPONSE), streaming=False)

    result = await model._agenerate([HumanMessage(content="hello")])

    assert result.generations[0].message.content == "hello"
    attributes = dict(telemetry.span(CHAT).attributes or {})
    assert attributes["gen_ai.request.stream"] is False
    assert attributes["gen_ai.usage.input_tokens"] == 40
    assert "gen_ai.response.time_to_first_chunk" not in attributes


async def test_streaming_through_agenerate_does_not_create_a_second_span(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_stream()), streaming=True)

    await model._agenerate([HumanMessage(content="hello")])

    assert [span.name for span in telemetry.spans()] == [CHAT]


async def test_an_empty_stream_retry_is_an_event_not_a_second_span(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_stream([]), _stream()), streaming=True)
    model.empty_retry_max_attempts = 2

    assert await _drain(model) == "hello"

    span = telemetry.span(CHAT)
    assert [(e.name, dict(e.attributes or {})) for e in span.events] == [
        ("attempt_failed", {"retry.attempt": 1, "error.type": "EmptyStreamError"})
    ]
    assert span.status.status_code is StatusCode.UNSET
    assert len(telemetry.metric_points("gen_ai.client.operation.duration")) == 1


async def test_a_provider_failure_is_an_error_span_without_the_message(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_fail(RuntimeError("provider says secret-token"))), streaming=False)
    model.empty_retry_enabled = False

    with pytest.raises(RuntimeError, match="secret-token"):
        await model._agenerate([HumanMessage(content="hello")])

    span = telemetry.span(CHAT)
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "RuntimeError"
    assert "secret-token" not in str(span.attributes) + str([dict(e.attributes or {}) for e in span.events])
    [point] = telemetry.metric_points("gen_ai.client.operation.duration")
    assert point["attributes"]["error.type"] == "RuntimeError"


async def test_a_streaming_failure_is_an_error_span(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_fail(ValueError("bad request"))), streaming=True)
    model.empty_retry_enabled = False

    with pytest.raises(ValueError, match="bad request"):
        await _drain(model)

    assert telemetry.span(CHAT).status.description == "ValueError"


async def test_a_consumer_that_abandons_the_stream_leaves_a_cancelled_span(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_stream()), streaming=True)

    stream = model._astream([HumanMessage(content="hello")])
    await stream.__anext__()
    await stream.aclose()

    span = telemetry.span(CHAT)
    assert span.attributes is not None and span.attributes["error.type"] == "cancelled"
    assert span.status.status_code is StatusCode.UNSET
    assert len(telemetry.metric_points("gen_ai.client.operation.duration")) == 1


async def test_the_span_is_complete_once_the_response_is_complete(telemetry: MemoryTelemetry) -> None:
    """Stopping after the last content chunk must not turn a finished response into a cancellation."""
    model = _model(FakeClient(_stream()), streaming=True)

    stream = model._astream([HumanMessage(content="hello")])
    chunks = [chunk async for chunk in stream]
    await stream.aclose()

    assert chunks
    span = telemetry.span(CHAT)
    assert span.attributes is not None and "error.type" not in span.attributes
    assert span.attributes["gen_ai.usage.input_tokens"] == 40


async def test_a_replayed_answer_creates_no_span_and_no_metrics(telemetry: MemoryTelemetry) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        client = FakeClient(_stream())
        model = _model(client, streaming=True)

        with llm_call_scope(LlmCallScope(session_id="s", turn_id="t", ledger=ledger)):
            await _drain(model)
        with llm_call_scope(LlmCallScope(session_id="s", turn_id="t", ledger=ledger)):
            assert await _drain(model) == "hello"

    assert client.calls == 1
    assert [span.name for span in telemetry.spans()] == [CHAT]
    assert len(telemetry.metric_points("gen_ai.client.operation.duration")) == 1
    assert sum(p["sum"] for p in telemetry.metric_points("gen_ai.client.token.usage")) == 48


async def test_model_calls_nest_under_the_agent_run_even_from_a_spawned_task(telemetry: MemoryTelemetry) -> None:
    model = _model(FakeClient(_stream()), streaming=True)
    agent = AgentRunSpan(agent_type="SkillAgent", query="q", context_values={"session_id": "conv"}, message_id=None)

    async def executor() -> None:
        await _drain(model)

    async def events() -> AsyncIterator[str]:
        await asyncio.create_task(executor())
        yield "done"

    async for _ in agent.scope(events()):
        pass
    agent.end()

    assert telemetry.parent_name(telemetry.span(CHAT)) == "invoke_agent SkillAgent"


async def test_prompt_and_reply_are_recorded_only_when_the_operator_opts_in(
    telemetry: MemoryTelemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = [SystemMessage(content="secret persona"), HumanMessage(content="my question")]

    await _model(FakeClient(_stream()), streaming=True)._agenerate(messages)
    assert "my question" not in str(telemetry.span(CHAT).attributes)

    telemetry.span_exporter.clear()
    monkeypatch.setenv(CAPTURE_CONTENT_ENV, "true")
    await _model(FakeClient(_stream()), streaming=True)._agenerate(messages)
    recorded = telemetry.span(CHAT).attributes or {}
    assert "my question" in str(recorded["gen_ai.input.messages"])
    assert "hello" in str(recorded["gen_ai.output.messages"])
    assert "secret persona" not in str(recorded)
