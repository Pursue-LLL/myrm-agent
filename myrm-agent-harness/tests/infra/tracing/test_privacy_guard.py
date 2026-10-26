"""The exporter-boundary privacy guard: metadata crosses, content does not, nothing leaves raw."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai.content import CAPTURE_CONTENT_ENV
from myrm_agent_harness.infra.tracing.otlp import privacy
from myrm_agent_harness.infra.tracing.otlp.privacy import PrivacyGuardExporter, sanitize_span

PROMPT = json.dumps([{"role": "user", "parts": [{"type": "text", "content": "my card number is 4111111111111111"}]}])


def _finished(build) -> ReadableSpan:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    tracer = provider.get_tracer("tests.privacy")
    with tracer.start_as_current_span("chat m", kind=SpanKind.CLIENT, record_exception=False) as span:
        build(span)
    return memory.get_finished_spans()[0]


def _content_span(span) -> None:
    span.set_attributes(
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-x",
            "gen_ai.usage.input_tokens": 120,
            "gen_ai.request.stream": True,
            "latency_ms": 3.5,
            "gen_ai.input.messages": PROMPT,
            "gen_ai.output.messages": "the answer is 42",
            "gen_ai.tool.call.arguments": '{"query": "private question"}',
            "gen_ai.tool.call.result": "private result",
            "gen_ai.system_instructions": "you are a secret persona",
            "gen_ai.prompt.0.content": "legacy prompt",
            "gen_ai.completion.0.content": "legacy completion",
            "input.value": "third-party prompt",
            "output.value": "third-party reply",
            "llm.input_messages.0.message.content": "openinference prompt",
            "metadata": '{"user": "someone"}',
            "agent.status": "completed",
        }
    )


def test_by_default_only_metadata_crosses_the_boundary() -> None:
    kept = sanitize_span(_finished(_content_span), capture_content=False).attributes

    assert kept == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gpt-x",
        "gen_ai.usage.input_tokens": 120,
        "gen_ai.request.stream": True,
        "latency_ms": 3.5,
        "agent.status": "completed",
    }


def test_content_capture_releases_content_but_never_the_system_prompt() -> None:
    kept = sanitize_span(_finished(_content_span), capture_content=True).attributes

    assert kept["gen_ai.input.messages"] == PROMPT
    assert kept["gen_ai.output.messages"] == "the answer is 42"
    assert kept["input.value"] == "third-party prompt"
    assert "gen_ai.system_instructions" not in kept


def test_captured_content_is_still_credential_redacted_and_bounded() -> None:
    def build(span) -> None:
        span.set_attribute("gen_ai.input.messages", "call with Authorization: Bearer abcdef0123456789abcdef")
        span.set_attribute("gen_ai.output.messages", "x" * 40000)

    kept = sanitize_span(_finished(build), capture_content=True).attributes

    assert "abcdef0123456789abcdef" not in str(kept["gen_ai.input.messages"])
    assert "[TRUNCATED:len=40000" in str(kept["gen_ai.output.messages"])


def test_metadata_text_is_credential_redacted() -> None:
    def build(span) -> None:
        span.set_attribute("http.url", "https://u:pw@host/x?api_key=SECRET123456")

    kept = sanitize_span(_finished(build), capture_content=False).attributes

    assert "SECRET123456" not in str(kept["http.url"])
    assert ":pw@" not in str(kept["http.url"])


def test_event_and_link_payloads_are_cleaned_like_span_attributes() -> None:
    other = _finished(lambda span: None).context

    def build(span) -> None:
        span.add_event("attempt_failed", {"retry.attempt": 2, "error.type": "RateLimitError", "note": "free text"})
        span.add_event(
            "exception",
            {
                "exception.type": "ValueError",
                "exception.message": "bad input: my card number is 4111111111111111",
                "exception.stacktrace": 'File "x.py", line 1\nValueError: my card number',
            },
        )
        span.add_event("gen_ai.content.prompt", {"gen_ai.prompt": "legacy prompt event"})
        span.add_link(other, {"gen_ai.input.messages": PROMPT, "agent.status": "completed"})

    sanitized = sanitize_span(_finished(build), capture_content=False)
    events = {event.name: dict(event.attributes or {}) for event in sanitized.events}

    assert events["attempt_failed"] == {"retry.attempt": 2, "error.type": "RateLimitError"}
    assert events["exception"] == {"exception.type": "ValueError"}
    assert events["gen_ai.content.prompt"] == {}
    assert [dict(link.attributes or {}) for link in sanitized.links] == [{"agent.status": "completed"}]
    assert all(isinstance(link, Link) for link in sanitized.links)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("ValueError: my card number is 4111111111111111", "ValueError"),
        ("openai.RateLimitError: slow down", "openai.RateLimitError"),
        ("free text with spaces and 4111111111111111", None),
        (None, None),
    ],
)
def test_error_status_keeps_the_class_name_but_not_the_message(description: str | None, expected: str | None) -> None:
    def build(span) -> None:
        span.set_status(Status(StatusCode.ERROR, description))

    status = sanitize_span(_finished(build), capture_content=False).status

    assert status.status_code is StatusCode.ERROR
    assert status.description == expected


def test_non_error_status_never_carries_a_description() -> None:
    def build(span) -> None:
        span.set_status(Status(StatusCode.OK))

    assert sanitize_span(_finished(build), capture_content=False).status.status_code is StatusCode.OK


def test_the_finished_span_itself_is_left_untouched() -> None:
    original = _finished(_content_span)
    sanitize_span(original, capture_content=False)

    assert original.attributes is not None
    assert original.attributes["gen_ai.input.messages"] == PROMPT


class _Recording(SpanExporter):
    def __init__(self, result: SpanExportResult = SpanExportResult.SUCCESS, *, raises: bool = False) -> None:
        self.batches: list[Sequence[ReadableSpan]] = []
        self._result = result
        self._raises = raises
        self.flushed = False
        self.closed = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.batches.append(list(spans))
        if self._raises:
            raise RuntimeError("collector exploded with secret-token")
        return self._result

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self.flushed = True
        return True

    def shutdown(self) -> None:
        self.closed = True


def test_the_exporter_only_ever_sees_sanitized_copies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CAPTURE_CONTENT_ENV, raising=False)
    inner = _Recording()
    guard = PrivacyGuardExporter(inner)

    assert guard.export([_finished(_content_span)]) is SpanExportResult.SUCCESS

    sent = inner.batches[0][0].attributes
    assert sent is not None and "gen_ai.input.messages" not in sent and "input.value" not in sent
    assert guard.stats().exported_spans == 1


def test_the_capture_switch_is_read_on_every_export(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = _Recording()
    guard = PrivacyGuardExporter(inner)
    span = _finished(_content_span)

    guard.export([span])
    monkeypatch.setenv(CAPTURE_CONTENT_ENV, "true")
    guard.export([span])

    first, second = (batch[0].attributes or {} for batch in inner.batches)
    assert "gen_ai.input.messages" not in first
    assert second["gen_ai.input.messages"] == PROMPT


def test_a_span_that_cannot_be_sanitized_is_withheld_never_sent_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    good, bad = _finished(lambda span: span.set_attribute("agent.status", "completed")), _finished(_content_span)
    real = privacy.sanitize_span

    def flaky(span: ReadableSpan, *, capture_content: bool) -> ReadableSpan:
        if span is bad:
            raise RuntimeError("sanitizer bug")
        return real(span, capture_content=capture_content)

    monkeypatch.setattr(privacy, "sanitize_span", flaky)
    inner = _Recording()
    guard = PrivacyGuardExporter(inner)

    guard.export([bad, good])

    assert [len(batch) for batch in inner.batches] == [1]
    assert inner.batches[0][0].attributes == {"agent.status": "completed"}
    assert guard.stats().withheld_spans == 1


def test_a_batch_where_every_span_is_withheld_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(privacy, "sanitize_span", lambda span, *, capture_content: 1 / 0)
    inner = _Recording()
    guard = PrivacyGuardExporter(inner)

    assert guard.export([_finished(_content_span)]) is SpanExportResult.SUCCESS
    assert inner.batches == []
    assert guard.stats().withheld_spans == 1


def test_export_failures_are_counted_and_do_not_leak_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    guard = PrivacyGuardExporter(_Recording(raises=True))

    with caplog.at_level("WARNING"):
        assert guard.export([_finished(_content_span)]) is SpanExportResult.FAILURE

    stats = guard.stats()
    assert stats.failed_batches == 1 and stats.exported_spans == 0 and stats.last_export_failed
    assert "secret-token" not in caplog.text


def test_a_rejecting_collector_counts_as_a_failed_batch() -> None:
    guard = PrivacyGuardExporter(_Recording(SpanExportResult.FAILURE))

    guard.export([_finished(_content_span)])

    assert guard.stats().failed_batches == 1


def test_lifecycle_calls_reach_the_wrapped_exporter() -> None:
    inner = _Recording()
    guard = PrivacyGuardExporter(inner)

    assert guard.force_flush() is True
    guard.shutdown()

    assert inner.flushed and inner.closed
