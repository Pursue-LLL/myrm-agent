"""Isolation for the process-global telemetry state and in-process OTLP receivers.

OpenTelemetry installs a tracer/meter provider once per process and the harness keeps its own
posture state next to it. Every test here starts from "nothing installed, no OTEL_* environment"
and hands the process back the same way, so a failure cannot leak a provider into the next test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TypedDict

import pytest
from opentelemetry import metrics, trace
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Sampler
from opentelemetry.util._once import Once

from myrm_agent_harness.infra.tracing import tracer
from myrm_agent_harness.infra.tracing.gen_ai import metrics as gen_ai_metrics
from myrm_agent_harness.infra.tracing.metrics import exporter as metrics_exporter
from myrm_agent_harness.infra.tracing.otlp import posture

from ._receivers import OtlpGrpcReceiver, OtlpHttpReceiver


class MetricPoint(TypedDict):
    """One histogram data point as the tests read it."""

    attributes: Mapping[str, object]
    count: int
    sum: float


def reset_telemetry() -> None:
    """Shut real providers down, then forget every provider and posture the process holds."""
    tracer.shutdown_tracing(timeout_ms=3000)
    metrics_exporter.shutdown_metrics(timeout_ms=3000)
    tracer._initialized = False
    tracer._tracer_provider = None
    metrics_exporter._initialized = False
    metrics_exporter._meter_provider = None
    posture.reset_traces()
    posture.reset_metrics()
    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics_internal._METER_PROVIDER_SET_ONCE = Once()
    metrics_internal._METER_PROVIDER = None
    gen_ai_metrics._instruments.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [key for key in os.environ if key.startswith("OTEL_")]:
        monkeypatch.delenv(name)
    monkeypatch.delenv("MYRM_LOCAL_TRACE_ONLY", raising=False)
    reset_telemetry()
    yield
    reset_telemetry()


@dataclass
class MemoryTelemetry:
    """Providers installed process-wide that keep everything in memory for assertions."""

    span_exporter: InMemorySpanExporter
    metric_reader: InMemoryMetricReader

    def spans(self) -> list[ReadableSpan]:
        return list(self.span_exporter.get_finished_spans())

    def span(self, name: str) -> ReadableSpan:
        matches = [span for span in self.spans() if span.name == name]
        assert len(matches) == 1, f"expected one span named {name!r}, got {[s.name for s in self.spans()]}"
        return matches[0]

    def parent_name(self, span: ReadableSpan) -> str | None:
        if span.parent is None:
            return None
        return next(other.name for other in self.spans() if other.context.span_id == span.parent.span_id)

    def metric_points(self, name: str) -> list[MetricPoint]:
        data = self.metric_reader.get_metrics_data()
        points: list[MetricPoint] = []
        for resource_metrics in data.resource_metrics if data else []:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    if metric.name != name:
                        continue
                    for point in metric.data.data_points:
                        assert isinstance(point, HistogramDataPoint), f"{name} is not a histogram"
                        points.append(
                            MetricPoint(attributes=dict(point.attributes or {}), count=point.count, sum=point.sum)
                        )
        return points


def install_memory_telemetry(sampler: Sampler | None = None) -> MemoryTelemetry:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(sampler=sampler)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    return MemoryTelemetry(span_exporter, reader)


@pytest.fixture
def telemetry() -> MemoryTelemetry:
    return install_memory_telemetry()


@pytest.fixture
def http_receiver() -> Iterator[OtlpHttpReceiver]:
    receiver = OtlpHttpReceiver()
    receiver.start()
    yield receiver
    reset_telemetry()  # final batches must reach a live collector, not time out against a dead one
    receiver.stop()


@pytest.fixture
def grpc_receiver() -> Iterator[OtlpGrpcReceiver]:
    receiver = OtlpGrpcReceiver()
    receiver.start()
    yield receiver
    reset_telemetry()
    receiver.stop()
