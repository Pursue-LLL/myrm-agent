"""One `chat` span and one set of GenAI client metrics per logical model call."""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.trace import StatusCode

from myrm_agent_harness.infra.tracing.gen_ai import ModelCall, provider_name
from myrm_agent_harness.infra.tracing.gen_ai.content import CAPTURE_CONTENT_ENV

from .conftest import MemoryTelemetry, install_memory_telemetry, reset_telemetry

MESSAGES = [
    {"role": "system", "content": "you are a secret persona"},
    {"role": "user", "content": "my card number is 4111111111111111"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}],
    },
    {"role": "tool", "tool_call_id": "c1", "content": "tool says hi"},
]
RESPONSE = {
    "model": "gpt-x-2025-01",
    "choices": [
        {
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "the answer", "reasoning_content": "private thoughts"},
        }
    ],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "prompt_tokens_details": {"cached_tokens": 60},
        "cache_creation_input_tokens": 10,
        "completion_tokens_details": {"reasoning_tokens": 5},
    },
}


def _call(*, stream: bool = False, params: dict[str, object] | None = None) -> ModelCall:
    return ModelCall(
        model="gpt-x",
        provider="openai",
        stream=stream,
        params=params or {"max_tokens": 256, "temperature": 0.2},
        message_dicts=MESSAGES,
    )


def test_a_call_records_request_response_and_usage(telemetry: MemoryTelemetry) -> None:
    call = _call(stream=True)
    call.begin(1)
    call.finish(RESPONSE, time_to_first_chunk_s=0.25)
    call.close()

    span = telemetry.span("chat gpt-x")
    assert dict(span.attributes or {}) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": "gpt-x",
        "gen_ai.request.stream": True,
        "gen_ai.request.max_tokens": 256,
        "gen_ai.request.temperature": 0.2,
        "gen_ai.response.model": "gpt-x-2025-01",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.response.time_to_first_chunk": 0.25,
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 20,
        "gen_ai.usage.cache_read.input_tokens": 60,
        "gen_ai.usage.cache_creation.input_tokens": 10,
        "gen_ai.usage.reasoning.output_tokens": 5,
    }
    assert span.status.status_code is StatusCode.UNSET


def test_prompt_reply_and_reasoning_are_not_even_recorded_by_default(telemetry: MemoryTelemetry) -> None:
    call = _call()
    call.begin(1)
    call.finish(RESPONSE)
    call.close()

    recorded = str(telemetry.span("chat gpt-x").attributes)
    for private in ("card number", "the answer", "private thoughts", "secret persona", "tool says hi"):
        assert private not in recorded


def test_content_capture_records_messages_without_system_prompt_or_reasoning(
    telemetry: MemoryTelemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAPTURE_CONTENT_ENV, "true")
    call = _call()
    call.begin(1)
    call.finish(RESPONSE)
    call.close()

    recorded = telemetry.span("chat gpt-x").attributes or {}
    assert "card number" in str(recorded["gen_ai.input.messages"])
    assert "tool says hi" in str(recorded["gen_ai.input.messages"])
    assert "the answer" in str(recorded["gen_ai.output.messages"])
    assert "secret persona" not in str(recorded)
    assert "private thoughts" not in str(recorded)


def test_retries_are_events_on_one_span(telemetry: MemoryTelemetry) -> None:
    call = _call()
    call.begin(1)
    call.attempt_failed(ValueError("empty choices with secret"))
    call.begin(2)
    call.finish(RESPONSE)
    call.close()

    assert [span.name for span in telemetry.spans()] == ["chat gpt-x"]
    events = telemetry.span("chat gpt-x").events
    assert [(event.name, dict(event.attributes or {})) for event in events] == [
        ("attempt_failed", {"retry.attempt": 1, "error.type": "ValueError"})
    ]


def test_a_replayed_answer_is_no_model_call(telemetry: MemoryTelemetry) -> None:
    call = _call()
    call.close()

    assert telemetry.spans() == []
    assert telemetry.metric_points("gen_ai.client.operation.duration") == []
    assert telemetry.metric_points("gen_ai.client.token.usage") == []


def test_a_failed_call_records_the_class_and_not_the_message(telemetry: MemoryTelemetry) -> None:
    call = _call()
    call.begin(1)
    call.fail(RuntimeError("leaks secret-token"))
    call.close()

    span = telemetry.span("chat gpt-x")
    assert span.attributes is not None and span.attributes["error.type"] == "RuntimeError"
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "RuntimeError"
    assert "secret-token" not in str(span.attributes) + str(span.status.description)
    [point] = telemetry.metric_points("gen_ai.client.operation.duration")
    assert point["attributes"]["error.type"] == "RuntimeError"


@pytest.mark.parametrize("exc", [asyncio.CancelledError(), GeneratorExit()])
def test_cancellation_and_abandonment_are_not_errors(telemetry: MemoryTelemetry, exc: BaseException) -> None:
    call = _call()
    call.begin(1)
    call.fail(exc)
    call.close()

    span = telemetry.span("chat gpt-x")
    assert span.attributes is not None and span.attributes["error.type"] == "cancelled"
    assert span.status.status_code is StatusCode.UNSET


def test_a_stream_abandoned_after_the_response_completed_stays_a_success(telemetry: MemoryTelemetry) -> None:
    call = _call(stream=True)
    call.begin(1)
    call.finish(RESPONSE, time_to_first_chunk_s=0.1)
    call.close()
    call.fail(GeneratorExit())
    call.attempt_failed(GeneratorExit())

    span = telemetry.span("chat gpt-x")
    assert span.attributes is not None and "error.type" not in span.attributes
    assert span.status.status_code is StatusCode.UNSET
    assert not span.events


def test_closing_twice_records_once(telemetry: MemoryTelemetry) -> None:
    call = _call()
    call.begin(1)
    call.finish(RESPONSE)
    call.close()
    call.close()

    assert len(telemetry.spans()) == 1
    assert len(telemetry.metric_points("gen_ai.client.operation.duration")) == 1


def test_the_three_standard_client_metrics_are_recorded_with_bounded_dimensions(telemetry: MemoryTelemetry) -> None:
    call = _call(stream=True)
    call.begin(1)
    call.finish(RESPONSE, time_to_first_chunk_s=0.25)
    call.close()

    dimensions = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "gen_ai.request.model": "gpt-x",
        "gen_ai.response.model": "gpt-x-2025-01",
    }
    [duration] = telemetry.metric_points("gen_ai.client.operation.duration")
    [first_chunk] = telemetry.metric_points("gen_ai.client.operation.time_to_first_chunk")
    tokens = {p["attributes"]["gen_ai.token.type"]: p for p in telemetry.metric_points("gen_ai.client.token.usage")}

    assert duration["attributes"] == dimensions
    assert first_chunk["attributes"] == dimensions and first_chunk["sum"] == 0.25
    assert tokens["input"]["sum"] == 100 and tokens["output"]["sum"] == 20
    assert tokens["input"]["attributes"] == {**dimensions, "gen_ai.token.type": "input"}


def test_a_non_streaming_call_records_no_first_chunk_measurement(telemetry: MemoryTelemetry) -> None:
    call = _call(stream=False)
    call.begin(1)
    call.finish(RESPONSE)
    call.close()

    assert telemetry.metric_points("gen_ai.client.operation.time_to_first_chunk") == []


def test_metrics_do_not_depend_on_trace_sampling() -> None:
    reset_telemetry()
    unsampled = install_memory_telemetry(sampler=ALWAYS_OFF)
    call = _call()
    call.begin(1)
    call.finish(RESPONSE)
    call.close()

    assert unsampled.spans() == []
    assert len(unsampled.metric_points("gen_ai.client.operation.duration")) == 1
    assert len(unsampled.metric_points("gen_ai.client.token.usage")) == 2


def test_model_calls_cost_nothing_when_nothing_listens() -> None:
    call = _call()
    call.begin(1)
    call.finish(RESPONSE)
    call.fail(RuntimeError("late"))
    call.close()


@pytest.mark.parametrize(
    ("custom_provider", "model", "expected"),
    [
        (None, "openai/gpt-4o", "openai"),
        ("bedrock", "anthropic.claude", "aws.bedrock"),
        ("azure", "gpt-4", "azure.ai.openai"),
        ("vertex_ai", "gemini-2", "gcp.vertex_ai"),
        ("xai", "grok", "x_ai"),
        (None, "plain-model", "unknown"),
        ("anthropic", "claude", "anthropic"),
    ],
)
def test_provider_names_follow_the_genai_conventions(custom_provider: str | None, model: str, expected: str) -> None:
    assert provider_name(custom_provider, model) == expected
