"""One `chat` span (and its metrics) for one logical model call.

[INPUT]
- opentelemetry.trace (POS: tracer API; a no-op until the host installs a TracerProvider)
- gen_ai.conventions / gen_ai.content / gen_ai.metrics (POS: names, opt-in content, client metrics)
- utils.token_economics.usage_fields (POS: single reader of provider usage fields)

[OUTPUT]
- ModelCall: begin / attempt_failed / finish / fail / close lifecycle of one logical model call

[POS]
The adapter reports what happened; this module decides how it is told. A logical call is one
`chat {model}` span however many attempts it took: empty-response and parameter-recovery retries
appear as events on the span rather than as sibling spans. The span starts at the first real
request (a replayed answer is no model call, so it creates no span and no measurement) and is
never made the current span, so nothing can leak across the generator boundaries of the streaming
path. Usage, response model and time to first chunk are written once, from the provider's
response. Error text is deliberately not recorded; only the error class is.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai import metrics as gen_ai_metrics
from myrm_agent_harness.infra.tracing.gen_ai.content import (
    capture_content_enabled,
    input_messages_json,
    output_messages_json,
)
from myrm_agent_harness.infra.tracing.gen_ai.conventions import (
    ERROR_TYPE,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_OPERATION_NAME,
    GEN_AI_OUTPUT_MESSAGES,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_STREAM,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_RESPONSE_TIME_TO_FIRST_CHUNK,
    GEN_AI_TRACER_NAME,
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    GEN_AI_USAGE_REASONING_OUTPUT_TOKENS,
    OP_CHAT,
    chat_span_name,
)
from myrm_agent_harness.utils.coercion import parse_int
from myrm_agent_harness.utils.token_economics.usage_fields import (
    extract_cache_write_tokens,
    extract_cached_tokens,
    extract_reasoning_tokens,
)

CANCELLED = "cancelled"

# LiteLLM provider ids that the GenAI conventions name differently.
_PROVIDER_NAMES: dict[str, str] = {
    "bedrock": "aws.bedrock",
    "azure": "azure.ai.openai",
    "vertex_ai": "gcp.vertex_ai",
    "gemini": "gcp.gemini",
    "xai": "x_ai",
    "mistral": "mistral_ai",
}


def provider_name(custom_llm_provider: str | None, model: str) -> str:
    """GenAI provider name from the LiteLLM provider id, or the ``provider/model`` prefix."""
    raw = custom_llm_provider or (model.partition("/")[0] if "/" in model else "")
    return _PROVIDER_NAMES.get(raw, raw) or "unknown"


def error_class(exc: BaseException) -> str:
    """Low-cardinality error label; a cancelled or abandoned call is not an error."""
    if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
        return CANCELLED
    return type(exc).__name__


class ModelCall:
    """Lifecycle of one logical model call; see the module docstring for the contract."""

    def __init__(
        self,
        *,
        model: str,
        provider: str,
        stream: bool,
        params: Mapping[str, object],
        message_dicts: Sequence[Mapping[str, object]],
    ) -> None:
        self._model = model
        self._provider = provider
        self._stream = stream
        self._params: Mapping[str, object] | None = params
        self._message_dicts: Sequence[Mapping[str, object]] | None = message_dicts
        self._span: Span | None = None
        self._started = 0.0
        self._attempt = 0
        self._response_model: str | None = None
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._time_to_first_chunk_s: float | None = None
        self._error_type: str | None = None
        self._closed = False

    def begin(self, attempt: int) -> None:
        """Mark the start of a real request; the first one opens the span."""
        self._attempt = attempt
        if self._span is not None:
            return
        attributes: dict[str, str | int | float | bool] = {
            GEN_AI_OPERATION_NAME: OP_CHAT,
            GEN_AI_PROVIDER_NAME: self._provider,
            GEN_AI_REQUEST_MODEL: self._model,
            GEN_AI_REQUEST_STREAM: self._stream,
        }
        params = self._params or {}
        max_tokens = params.get("max_tokens") or params.get("max_completion_tokens")
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
            attributes[GEN_AI_REQUEST_MAX_TOKENS] = max_tokens
        temperature = params.get("temperature")
        if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
            attributes[GEN_AI_REQUEST_TEMPERATURE] = float(temperature)
        if capture_content_enabled() and self._message_dicts is not None:
            attributes[GEN_AI_INPUT_MESSAGES] = input_messages_json(self._message_dicts)
        self._params = self._message_dicts = None
        tracer = trace.get_tracer(GEN_AI_TRACER_NAME)
        self._span = tracer.start_span(chat_span_name(self._model), kind=SpanKind.CLIENT, attributes=attributes)
        self._started = time.perf_counter()

    def attempt_failed(self, exc: BaseException) -> None:
        """Record a failed attempt; whether it was retried shows in the next attempt's events."""
        if self._span is not None and not self._closed:
            self._span.add_event("attempt_failed", {"retry.attempt": self._attempt, ERROR_TYPE: error_class(exc)})

    def finish(self, response: Mapping[str, object], *, time_to_first_chunk_s: float | None = None) -> None:
        """Record the provider's response: model, finish reason, usage and (opt-in) content."""
        span = self._span
        if span is None or self._closed:
            return
        model = response.get("model")
        if isinstance(model, str) and model:
            self._response_model = model
            span.set_attribute(GEN_AI_RESPONSE_MODEL, model)
        choices = response.get("choices")
        first = choices[0] if isinstance(choices, Sequence) and choices and isinstance(choices[0], Mapping) else {}
        if isinstance(reason := first.get("finish_reason"), str) and reason:
            span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [reason])
        if time_to_first_chunk_s is not None:
            self._time_to_first_chunk_s = time_to_first_chunk_s
            span.set_attribute(GEN_AI_RESPONSE_TIME_TO_FIRST_CHUNK, time_to_first_chunk_s)
        usage = response.get("usage")
        if isinstance(usage, Mapping) and usage:
            self._record_usage(span, usage)
        if capture_content_enabled():
            span.set_attribute(GEN_AI_OUTPUT_MESSAGES, output_messages_json(response))

    def _record_usage(self, span: Span, usage: Mapping[str, object]) -> None:
        if "prompt_tokens" in usage:
            self._input_tokens = parse_int(usage.get("prompt_tokens"), 0, min_val=0)
            span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, self._input_tokens)
        if "completion_tokens" in usage:
            self._output_tokens = parse_int(usage.get("completion_tokens"), 0, min_val=0)
            span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, self._output_tokens)
        for name, count in (
            (GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS, extract_cached_tokens(usage)),
            (GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS, extract_cache_write_tokens(usage)),
            (GEN_AI_USAGE_REASONING_OUTPUT_TOKENS, extract_reasoning_tokens(usage)),
        ):
            if count:
                span.set_attribute(name, count)

    def fail(self, exc: BaseException) -> None:
        """Record that the call ended without a usable response.

        A call that already closed is complete: an abandoned stream cannot turn its finished
        response into an error.
        """
        if self._closed:
            return
        self._error_type = error_class(exc)
        span = self._span
        if span is None:
            return
        span.set_attribute(ERROR_TYPE, self._error_type)
        if self._error_type != CANCELLED:
            span.set_status(Status(StatusCode.ERROR, self._error_type))

    def close(self) -> None:
        """End the span and record the metrics; safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        span = self._span
        if span is None:
            return
        span.end()
        gen_ai_metrics.record_model_call(
            request_model=self._model,
            provider=self._provider,
            response_model=self._response_model,
            duration_s=time.perf_counter() - self._started,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            time_to_first_chunk_s=self._time_to_first_chunk_s,
            error_type=self._error_type,
        )
