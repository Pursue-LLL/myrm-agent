"""Sampling is the SDK's own: standard ``OTEL_TRACES_SAMPLER*`` variables or an explicit sampler argument."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

from myrm_agent_harness.infra.tracing import (
    force_flush_tracing,
    get_telemetry_posture,
    setup_tracing,
    trace_context,
)

from ._receivers import OtlpHttpReceiver


def _emit_one_span() -> None:
    with trace_context("tests.sampling", "op"):
        pass
    assert force_flush_tracing(timeout_ms=5000)


def test_every_span_is_kept_by_default(http_receiver: OtlpHttpReceiver) -> None:
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    _emit_one_span()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    assert "AlwaysOnSampler" in str(get_telemetry_posture()["sampler"])


@pytest.mark.parametrize(
    ("sampler", "argument", "expected"),
    [
        ("always_off", None, "AlwaysOffSampler"),
        ("parentbased_traceidratio", "0.0", "TraceIdRatioBased{0.0}"),
    ],
)
def test_standard_sampler_variables_drop_spans(
    http_receiver: OtlpHttpReceiver,
    monkeypatch: pytest.MonkeyPatch,
    sampler: str,
    argument: str | None,
    expected: str,
) -> None:
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", sampler)
    if argument is not None:
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", argument)
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    _emit_one_span()

    assert expected in str(get_telemetry_posture()["sampler"])
    assert http_receiver.spans() == []


def test_a_ratio_of_one_keeps_every_span(http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "parentbased_traceidratio")
    monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "1.0")
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    _emit_one_span()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))


def test_an_explicit_sampler_wins_over_the_environment(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    setup_tracing(otlp_endpoint=http_receiver.endpoint, sampler=ALWAYS_OFF)
    _emit_one_span()

    assert http_receiver.spans() == []
    assert "AlwaysOffSampler" in str(get_telemetry_posture()["sampler"])


def test_the_retired_custom_rate_variable_has_no_effect(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_SAMPLE_RATE", "0.0")
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    _emit_one_span()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
