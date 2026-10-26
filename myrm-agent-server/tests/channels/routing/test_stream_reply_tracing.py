"""One streamed reply is one trace.

Every streamed text event used to open a span of its own with nothing around it, so a backend showed a handful of
disconnected one-span traces per reply and the agent run as yet another trace. The consumption now runs inside a
single reply span: the agent run and every edit nest below it, the numbers of the session end up on it, and a
failure is recorded by class only (its message can echo the sender's text).
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracerProvider, StatusCode, Tracer

from app.channels.routing.router import AgentRouter
from app.channels.routing.stream_manager import UpdateDecision
from app.channels.routing.stream_metrics import stream_reply_span
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate, StreamingText

_REPLY = "Your refund is approved and will reach your card within five days of today."
_DELTAS = 3


@dataclass(frozen=True)
class _Telemetry:
    exporter: InMemorySpanExporter
    tracer: Tracer

    def spans(self) -> list[ReadableSpan]:
        return list(self.exporter.get_finished_spans())

    def only(self, name: str) -> ReadableSpan:
        (found,) = [span for span in self.spans() if span.name == name]
        return found


@pytest.fixture
def telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Telemetry]:
    """A private provider behind both tracer lookups of the stream path, so no global state is touched."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr("app.channels.routing.stream_metrics.get_tracer", provider.get_tracer)
    monkeypatch.setattr("myrm_agent_harness.infra.tracing.tracer.get_tracer", provider.get_tracer)
    yield _Telemetry(exporter, provider.get_tracer("test"))
    provider.shutdown()


class _Executor:
    """Plays a real turn: the agent run is a span of its own that nests wherever the consumer is."""

    def __init__(self, tracer: Tracer, *, deltas: int = _DELTAS, fail_with: Exception | None = None) -> None:
        self._tracer = tracer
        self._deltas = deltas
        self._fail_with = fail_with

    async def execute_stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncIterator[object]:
        with self._tracer.start_as_current_span("invoke_agent"):
            await asyncio.sleep(0)
        yield ProgressUpdate(label="Looking up your order")
        for step in range(1, self._deltas + 1):
            yield StreamingText(text=_REPLY[: 10 * step + 30])
        if self._fail_with is not None:
            raise self._fail_with
        yield OutboundMessage(channel=msg.channel, recipient_id=msg.chat_id or "", content=_REPLY, user_id=user_id)


def _inbound() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", content="where is my refund?", chat_id="chat-1", message_id="m1")


def _router(monkeypatch: pytest.MonkeyPatch, executor: _Executor, *, edits_succeed: bool = True) -> AgentRouter:
    """A real router whose chat edits are recorded instead of sent and whose every text event becomes an edit."""
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=None)
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=executor)
    monkeypatch.setattr(router._fx, "edit_progress", AsyncMock(return_value=edits_succeed))
    monkeypatch.setattr(router, "_try_throttled_edit", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_resolve_live_placeholder_id", lambda state_key: "placeholder-1")
    monkeypatch.setattr(router, "_mark_deferred_placeholder_activity", AsyncMock())
    monkeypatch.setattr(
        router._stream_coordinator,
        "should_send_update",
        MagicMock(return_value=UpdateDecision(should_send=True, reason="test")),
    )
    monkeypatch.setattr("app.channels.routing.router_stream.run_reassurance_loop", AsyncMock())
    return router


async def _stream(router: AgentRouter) -> OutboundMessage | None:
    result, _ = await router._consume_executor_stream(_inbound(), "guest_u1", "telegram:chat-1", "chat-1")
    return result


async def test_the_whole_reply_is_one_trace(telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch) -> None:
    result = await _stream(_router(monkeypatch, _Executor(telemetry.tracer)))

    assert result is not None and result.content == _REPLY
    spans = telemetry.spans()
    reply = telemetry.only("stream_reply")
    assert reply.parent is None
    assert {span.context.trace_id for span in spans} == {reply.context.trace_id}
    assert all(span.parent is not None for span in spans if span is not reply)
    # one span per streamed text event is gone; what remains is the run and the edits it caused
    assert Counter(span.name for span in spans) == {"stream_reply": 1, "invoke_agent": 1, "edit_with_retry": _DELTAS}


async def test_the_agent_run_and_every_edit_nest_under_the_reply_span(
    telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _stream(_router(monkeypatch, _Executor(telemetry.tracer)))

    reply_id = telemetry.only("stream_reply").context.span_id
    nested = [span for span in telemetry.spans() if span.name != "stream_reply"]
    assert [span.parent.span_id for span in nested if span.parent is not None] == [reply_id] * len(nested)


async def test_the_session_numbers_end_up_on_the_reply_span(telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch) -> None:
    await _stream(_router(monkeypatch, _Executor(telemetry.tracer)))

    assert dict(telemetry.only("stream_reply").attributes or {}) == {
        "myrm.channel": "telegram",
        "myrm.stream.update_decisions": _DELTAS,
        "myrm.stream.edits": _DELTAS,
        "myrm.stream.edit_failures": 0,
    }


async def test_a_failed_reply_records_the_error_class_only(telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "order 4471 refund to jane@example.com"
    router = _router(monkeypatch, _Executor(telemetry.tracer, fail_with=RuntimeError(secret)))

    with pytest.raises(RuntimeError):
        await _stream(router)

    reply = telemetry.only("stream_reply")
    assert reply.status.status_code is StatusCode.ERROR
    assert reply.status.description is None
    assert (reply.attributes or {})["error.type"] == "RuntimeError"
    assert reply.events == ()
    assert secret not in repr([(span.attributes, span.events, span.status) for span in telemetry.spans()])


async def test_a_cancelled_reply_is_not_an_error(telemetry: _Telemetry) -> None:
    with pytest.raises(asyncio.CancelledError), stream_reply_span("telegram"):
        raise asyncio.CancelledError

    assert telemetry.only("stream_reply").status.status_code is StatusCode.UNSET


async def test_the_fallback_is_marked_once_on_the_third_consecutive_failed_edit(
    telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = _router(monkeypatch, _Executor(telemetry.tracer, deltas=5))
    monkeypatch.setattr(router, "_try_edit_with_retry", AsyncMock(return_value=False))

    await _stream(router)

    reply = telemetry.only("stream_reply")
    assert [(event.name, dict(event.attributes or {})) for event in reply.events] == [
        ("fallback_to_new_message", {"consecutive_failures": 3})
    ]
    assert (reply.attributes or {})["myrm.stream.edit_failures"] == 3  # text events after the fallback add no edits


async def test_log_lines_carry_the_trace_id_of_the_reply(
    telemetry: _Telemetry, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="myrm.channels.routing.stream")

    await _stream(_router(monkeypatch, _Executor(telemetry.tracer)))

    expected = f"trace_id={telemetry.only('stream_reply').context.trace_id:032x}"
    completed = [record.getMessage() for record in caplog.records if record.getMessage().startswith("stream_completed ")]
    assert len(completed) == 1 and expected in completed[0]


async def test_a_reply_streams_the_same_when_nothing_records(monkeypatch: pytest.MonkeyPatch) -> None:
    noop = NoOpTracerProvider()
    monkeypatch.setattr("app.channels.routing.stream_metrics.get_tracer", noop.get_tracer)
    monkeypatch.setattr("myrm_agent_harness.infra.tracing.tracer.get_tracer", noop.get_tracer)

    result = await _stream(_router(monkeypatch, _Executor(noop.get_tracer("test"))))

    assert result is not None and result.content == _REPLY
