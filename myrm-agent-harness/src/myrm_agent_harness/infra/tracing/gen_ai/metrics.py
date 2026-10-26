"""Standard GenAI client metrics, recorded once per model call.

[INPUT]
- opentelemetry.metrics (POS: meter API; instruments are inert until the host installs a MeterProvider)
- gen_ai.conventions (POS: metric and attribute names)

[OUTPUT]
- record_model_call: token usage, operation duration and time to first chunk of one model call

[POS]
The three metrics the GenAI semantic conventions define for model clients. They are recorded from
the model call's own measurements, so they are independent of trace sampling and of whether a
trace exporter is configured. Dimensions are bounded (operation, provider, model, token type,
error class), which keeps the series count flat as conversations grow.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from opentelemetry import metrics
from opentelemetry.metrics import Histogram

from myrm_agent_harness.infra.tracing.gen_ai.conventions import (
    ERROR_TYPE,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_TOKEN_TYPE,
    METRIC_OPERATION_DURATION,
    METRIC_TIME_TO_FIRST_CHUNK,
    METRIC_TOKEN_USAGE,
    OP_CHAT,
    TOKEN_TYPE_INPUT,
    TOKEN_TYPE_OUTPUT,
)

_METER_NAME = "myrm_agent_harness.gen_ai"
# Bucket boundaries recommended by the GenAI semantic conventions.
_DURATION_BUCKETS = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]
_TOKEN_BUCKETS = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]


@dataclass(frozen=True, slots=True)
class _Instruments:
    token_usage: Histogram
    operation_duration: Histogram
    time_to_first_chunk: Histogram


@cache
def _instruments() -> _Instruments:
    meter = metrics.get_meter(_METER_NAME)
    return _Instruments(
        token_usage=meter.create_histogram(
            METRIC_TOKEN_USAGE,
            unit="{token}",
            description="Number of input and output tokens used by model calls",
            explicit_bucket_boundaries_advisory=_TOKEN_BUCKETS,
        ),
        operation_duration=meter.create_histogram(
            METRIC_OPERATION_DURATION,
            unit="s",
            description="Duration of model calls",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        ),
        time_to_first_chunk=meter.create_histogram(
            METRIC_TIME_TO_FIRST_CHUNK,
            unit="s",
            description="Time until the first streamed chunk of a model call",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        ),
    )


def record_model_call(
    *,
    request_model: str,
    provider: str,
    response_model: str | None,
    duration_s: float,
    input_tokens: int | None,
    output_tokens: int | None,
    time_to_first_chunk_s: float | None,
    error_type: str | None,
) -> None:
    """Record the measurements of one finished model call."""
    instruments = _instruments()
    attributes: dict[str, str] = {
        GEN_AI_OPERATION_NAME: OP_CHAT,
        GEN_AI_PROVIDER_NAME: provider,
        GEN_AI_REQUEST_MODEL: request_model,
    }
    if response_model:
        attributes[GEN_AI_RESPONSE_MODEL] = response_model
    instruments.operation_duration.record(
        duration_s, {**attributes, ERROR_TYPE: error_type} if error_type else attributes
    )
    if time_to_first_chunk_s is not None:
        instruments.time_to_first_chunk.record(time_to_first_chunk_s, attributes)
    if input_tokens is not None:
        instruments.token_usage.record(input_tokens, {**attributes, GEN_AI_TOKEN_TYPE: TOKEN_TYPE_INPUT})
    if output_tokens is not None:
        instruments.token_usage.record(output_tokens, {**attributes, GEN_AI_TOKEN_TYPE: TOKEN_TYPE_OUTPUT})
