"""Metrics export on the shared OTLP pipeline, plus the cardinality firewall of the collector."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.infra.tracing import is_tracing_initialized, setup_tracing
from myrm_agent_harness.infra.tracing.metrics import (
    force_flush_metrics,
    get_meter,
    get_meter_provider,
    is_metrics_initialized,
    sanitize_metric_labels,
    setup_metrics,
    shutdown_metrics,
)

from ._receivers import OtlpGrpcReceiver, OtlpHttpReceiver


def _record_and_flush() -> None:
    get_meter("tests.metrics").create_counter("tests.counter").add(3, {"tool": "bash"})
    assert force_flush_metrics(timeout_ms=5000)


def test_metrics_reach_an_http_collector_on_the_metrics_path(http_receiver: OtlpHttpReceiver) -> None:
    setup_metrics(service_name="svc-metrics", otlp_endpoint=http_receiver.endpoint)
    _record_and_flush()

    assert http_receiver.wait_for(lambda: bool(http_receiver.metrics()))
    assert http_receiver.paths() == ["/v1/metrics"]
    [metric] = [m for m in http_receiver.metrics() if m.name == "tests.counter"]
    assert metric.resource["service.name"] == "svc-metrics"
    assert metric.points == [{"tool": "bash", "__value": 3}]


def test_metrics_reach_a_grpc_collector(grpc_receiver: OtlpGrpcReceiver) -> None:
    setup_metrics(otlp_endpoint=grpc_receiver.endpoint, otlp_protocol="grpc")
    _record_and_flush()

    assert grpc_receiver.wait_for(lambda: any(m.name == "tests.counter" for m in grpc_receiver.metrics()))


def test_one_general_endpoint_serves_traces_and_metrics(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    from myrm_agent_harness.infra.tracing import force_flush_tracing, trace_context

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", http_receiver.endpoint)
    setup_tracing(service_name="svc-both")
    setup_metrics(service_name="svc-both")
    with trace_context("tests", "op"):
        pass
    assert force_flush_tracing(timeout_ms=5000)
    _record_and_flush()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()) and bool(http_receiver.metrics()))
    assert set(http_receiver.paths()) == {"/v1/traces", "/v1/metrics"}


def test_metrics_can_be_switched_off_without_touching_traces(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", http_receiver.endpoint)
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    setup_tracing()
    setup_metrics()

    assert is_tracing_initialized()
    assert not is_metrics_initialized()


def test_metrics_stay_off_without_a_destination() -> None:
    setup_metrics(service_name="svc-off")

    assert not is_metrics_initialized()
    assert get_meter_provider() is None


def test_the_kill_switch_turns_metrics_off(http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    setup_metrics(otlp_endpoint=http_receiver.endpoint)

    assert not is_metrics_initialized()


def test_a_missing_http_exporter_leaves_metrics_off_and_never_swaps_protocol(
    http_receiver: OtlpHttpReceiver, grpc_receiver: OtlpGrpcReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http.metric_exporter", None)
    setup_metrics(otlp_endpoint=http_receiver.endpoint)

    assert not is_metrics_initialized()
    assert http_receiver.requests == [] and grpc_receiver.requests == []


def test_a_remote_endpoint_is_refused_in_local_trace_only_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_LOCAL_TRACE_ONLY", "1")

    with pytest.raises(PermissionError):
        setup_metrics(otlp_endpoint="http://localhost.attacker.example:4318")


def test_console_export_for_development() -> None:
    setup_metrics(service_name="svc-console", console_export=True, export_interval_ms=1000)

    assert is_metrics_initialized()
    assert force_flush_metrics(timeout_ms=3000) is True


def test_setup_is_idempotent_and_shutdown_resets_the_accessors(http_receiver: OtlpHttpReceiver) -> None:
    assert not force_flush_metrics()
    setup_metrics(otlp_endpoint=http_receiver.endpoint)
    first = get_meter_provider()
    setup_metrics(otlp_endpoint=http_receiver.endpoint)

    assert is_metrics_initialized() and get_meter_provider() is first
    assert shutdown_metrics(timeout_ms=3000) is True
    assert not is_metrics_initialized() and get_meter_provider() is None


def test_sanitize_metric_labels_blocks_high_cardinality() -> None:
    """Verify CardinalityFirewall strips unbounded keys and preserves safe keys."""
    raw_labels = {
        "session_id": "sess_abc123",
        "turn_id": "turn_001",
        "workspace": "/home/user/my_project",
        "tool": "bash",
        "status": "success",
        "count": 42,
    }
    sanitized = sanitize_metric_labels(raw_labels)

    assert "session_id" not in sanitized
    assert "turn_id" not in sanitized
    assert "workspace" not in sanitized
    assert sanitized["tool"] == "bash"
    assert sanitized["status"] == "success"
    assert sanitized["count"] == "42"


def test_metrics_collector_with_cardinality_firewall() -> None:
    """Verify MetricsCollector transparently cleans high-cardinality labels."""
    from myrm_agent_harness.infra.tracing.metrics.collector import MetricsCollector

    mock_meter = MagicMock()
    mock_counter = MagicMock()
    mock_meter.create_counter.return_value = mock_counter

    collector = MetricsCollector(mock_meter)
    collector.counter(
        "agent.tool.calls",
        1,
        labels={"session_id": "sess-999", "tool": "file_read"},
    )

    mock_counter.add.assert_called_once_with(1, attributes={"tool": "file_read"})


def test_dynamic_label_manager_lru_and_threshold() -> None:
    """Verify DynamicLabelManager tracks frequent entities and falls back to 'other'."""
    from myrm_agent_harness.infra.tracing.metrics.cardinality import DynamicLabelManager

    manager = DynamicLabelManager(max_tracked=2, access_threshold=2)

    # First access - below threshold -> 'other'
    assert manager.get_label_value("model-a") == "other"
    # Second access - meets threshold -> tracked
    assert manager.get_label_value("model-a") == "model-a"

    # model-b first access -> 'other'
    assert manager.get_label_value("model-b") == "other"
    # model-b second access -> tracked (cache now has model-a, model-b)
    assert manager.get_label_value("model-b") == "model-b"

    # model-c first and second access - cache is full
    assert manager.get_label_value("model-c") == "other"
    # Third access to model-c (count 3) exceeds model-a/b (count 2), evicts least frequent
    assert manager.get_label_value("model-c") == "other"
    assert manager.get_label_value("model-c") == "model-c"

    # Test thread safety and utility functions
    assert len(manager.get_tracked_entities()) <= 2
    manager.clear()
    assert len(manager.get_tracked_entities()) == 0


def test_metrics_collector_gauge_and_histogram() -> None:
    """Verify MetricsCollector gauge and histogram methods sanitize labels properly."""
    from myrm_agent_harness.infra.tracing.metrics.collector import MetricsCollector

    mock_meter = MagicMock()
    mock_gauge = MagicMock()
    mock_histogram = MagicMock()
    mock_meter.create_gauge.return_value = mock_gauge
    mock_meter.create_histogram.return_value = mock_histogram

    collector = MetricsCollector(mock_meter)
    collector.gauge("agent.memory.mb", 512.0, labels={"session_id": "s1", "tier": "standard"})
    mock_gauge.record.assert_called_once_with(512.0, attributes={"tier": "standard"})

    collector.histogram("agent.turn.duration_ms", 120.5, labels={"workspace": "/tmp/ws", "status": "ok"})
    mock_histogram.record.assert_called_once_with(120.5, attributes={"status": "ok"})
