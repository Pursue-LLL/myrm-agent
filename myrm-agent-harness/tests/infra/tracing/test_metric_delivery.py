"""Whether the metric destination accepted the latest export, as the wrapper and the posture report it.

The periodic reader of the SDK ignores the outcome of an export, so a collector that refuses metrics (a
traces-only backend answers 404 on ``/v1/metrics``) must still show up as failing.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from opentelemetry.sdk.metrics import Counter
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)

from myrm_agent_harness.infra.tracing import (
    force_flush_tracing,
    get_telemetry_posture,
    setup_tracing,
    trace_context,
)
from myrm_agent_harness.infra.tracing.metrics import force_flush_metrics, get_meter, setup_metrics, shutdown_metrics
from myrm_agent_harness.infra.tracing.otlp import exporters
from myrm_agent_harness.infra.tracing.otlp.exporters import DeliveryTrackingMetricExporter
from myrm_agent_harness.infra.tracing.otlp.posture import build_posture, record_metrics
from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats

from ._receivers import OtlpHttpReceiver

_SECRET = "Bearer s3cr3t-token-value"
_EMPTY = MetricsData(resource_metrics=[])


class _ScriptedMetricExporter(MetricExporter):
    """A metric exporter whose outcome the test chooses."""

    def __init__(self, outcome: MetricExportResult | Exception = MetricExportResult.SUCCESS) -> None:
        super().__init__(preferred_temporality={Counter: AggregationTemporality.DELTA})
        self.outcome = outcome
        self.shutdown_kwargs: dict[str, object] | None = None

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: object) -> MetricExportResult:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        self.shutdown_kwargs = {"timeout_millis": timeout_millis, **kwargs}


@pytest.fixture
def ticking_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every reading of the wrapper's clock is later than the previous one, so outcomes are ordered."""
    readings = iter(float(second) for second in range(1, 100))
    monkeypatch.setattr(exporters, "time", SimpleNamespace(time=lambda: next(readings)))


@pytest.mark.usefixtures("ticking_clock")
def test_an_accepted_export_is_recorded_as_a_delivery() -> None:
    tracked = DeliveryTrackingMetricExporter(_ScriptedMetricExporter())
    assert not tracked.stats().attempted

    assert tracked.export(_EMPTY) is MetricExportResult.SUCCESS

    stats = tracked.stats()
    assert stats.attempted and not stats.last_export_failed
    assert stats.failed_batches == 0


@pytest.mark.usefixtures("ticking_clock")
def test_a_refused_export_is_a_failure_until_a_later_export_is_accepted() -> None:
    inner = _ScriptedMetricExporter(MetricExportResult.FAILURE)
    tracked = DeliveryTrackingMetricExporter(inner)

    assert tracked.export(_EMPTY) is MetricExportResult.FAILURE
    assert tracked.stats().last_export_failed
    assert tracked.stats().failed_batches == 1

    inner.outcome = MetricExportResult.SUCCESS
    tracked.export(_EMPTY)

    assert not tracked.stats().last_export_failed
    assert tracked.stats().failed_batches == 1


def test_an_exporter_that_raises_counts_as_failing_and_its_text_is_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tracked = DeliveryTrackingMetricExporter(_ScriptedMetricExporter(RuntimeError(f"rejected {_SECRET}")))

    with caplog.at_level(logging.WARNING, logger=exporters.logger.name):
        assert tracked.export(_EMPTY) is MetricExportResult.FAILURE

    assert tracked.stats().last_export_failed
    assert "RuntimeError" in caplog.text
    assert _SECRET not in caplog.text


def test_the_wrapper_keeps_the_temporality_of_the_exporter_it_wraps() -> None:
    reader = PeriodicExportingMetricReader(
        DeliveryTrackingMetricExporter(_ScriptedMetricExporter()), export_interval_millis=60_000
    )
    try:
        delta = [
            instrument
            for instrument, temporality in reader._instrument_class_temporality.items()
            if temporality is AggregationTemporality.DELTA
        ]
        assert [instrument.__name__ for instrument in delta] == ["_Counter"]
    finally:
        reader.shutdown()


def test_flush_and_shutdown_reach_the_wrapped_exporter() -> None:
    inner = _ScriptedMetricExporter()
    tracked = DeliveryTrackingMetricExporter(inner)

    assert tracked.force_flush(1000) is True
    tracked.shutdown(timeout=1.5)  # the reader's own keyword for the remaining time

    assert inner.shutdown_kwargs == {"timeout_millis": 30_000, "timeout": 1.5}


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        (ExportStats(), "ready"),
        (ExportStats(last_success_at=10.0), "active"),
        (ExportStats(failed_batches=1, last_failure_at=10.0), "failing"),
        (ExportStats(failed_batches=1, last_success_at=10.0, last_failure_at=20.0), "failing"),
        (ExportStats(failed_batches=1, last_success_at=30.0, last_failure_at=20.0), "active"),
    ],
)
def test_metrics_status_follows_the_latest_delivery_outcome(stats: ExportStats, expected: str) -> None:
    assert build_posture(initialized=False, has_sdk=True)["metrics_status"] == "off"

    record_metrics(stats=lambda: stats)

    assert build_posture(initialized=False, has_sdk=True)["metrics_status"] == expected


def _record_and_flush() -> None:
    get_meter("tests.metric_delivery").create_counter("tests.counter").add(1)
    assert force_flush_metrics(timeout_ms=5000)


def test_a_built_pipeline_is_ready_until_an_accepted_export_makes_it_active(http_receiver: OtlpHttpReceiver) -> None:
    setup_metrics(otlp_endpoint=http_receiver.endpoint)
    assert get_telemetry_posture()["metrics_status"] == "ready"

    _record_and_flush()

    assert http_receiver.wait_for(lambda: bool(http_receiver.metrics()))
    assert get_telemetry_posture()["metrics_status"] == "active"


def test_a_collector_that_refuses_metrics_is_failing_while_traces_stay_active(http_receiver: OtlpHttpReceiver) -> None:
    http_receiver.refused = ("/v1/metrics",)
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    setup_metrics(otlp_endpoint=http_receiver.endpoint)
    with trace_context("tests.metric_delivery", "op"):
        pass
    assert force_flush_tracing(timeout_ms=5000)
    _record_and_flush()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    posture = get_telemetry_posture()
    assert posture["status"] == "active"
    assert posture["metrics_status"] == "failing"


def test_a_metrics_collector_that_recovers_is_reported_active_again(http_receiver: OtlpHttpReceiver) -> None:
    http_receiver.status = 400
    setup_metrics(otlp_endpoint=http_receiver.endpoint)
    _record_and_flush()
    assert http_receiver.wait_for(lambda: bool(http_receiver.requests))
    assert get_telemetry_posture()["metrics_status"] == "failing"

    http_receiver.status = 200
    _record_and_flush()

    assert http_receiver.wait_for(lambda: get_telemetry_posture()["metrics_status"] == "active")


def test_metrics_status_is_off_without_a_pipeline_and_after_shutdown(http_receiver: OtlpHttpReceiver) -> None:
    setup_metrics()
    assert get_telemetry_posture()["metrics_status"] == "off"

    setup_metrics(otlp_endpoint=http_receiver.endpoint)
    assert get_telemetry_posture()["metrics_status"] == "ready"
    assert shutdown_metrics(timeout_ms=3000) is True

    assert get_telemetry_posture()["metrics_status"] == "off"
