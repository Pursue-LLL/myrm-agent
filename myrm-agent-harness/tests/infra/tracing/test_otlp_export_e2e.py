"""What a real OTLP collector receives: endpoint semantics, protocols, headers, resource, lifecycle."""

from __future__ import annotations

import sys

import pytest

from myrm_agent_harness.infra.tracing import (
    force_flush_tracing,
    get_telemetry_posture,
    is_tracing_initialized,
    setup_tracing,
    trace_context,
)

from ._receivers import OtlpGrpcReceiver, OtlpHttpReceiver


def _emit(name: str = "op") -> None:
    with trace_context("tests.otlp", name, {"agent.step": 1}):
        pass
    assert force_flush_tracing(timeout_ms=5000)


def test_http_is_the_default_protocol_and_posts_to_the_traces_path(http_receiver: OtlpHttpReceiver) -> None:
    setup_tracing(service_name="svc-a", otlp_endpoint=http_receiver.endpoint)
    _emit()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    assert http_receiver.paths() == ["/v1/traces"]
    span = http_receiver.spans()[0]
    assert span.name == "op"
    assert span.resource["service.name"] == "svc-a"
    assert span.attributes["agent.step"] == 1


def test_general_endpoint_from_the_environment_gets_the_signal_path(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", http_receiver.endpoint)
    setup_tracing(service_name="svc-env")
    _emit()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    assert http_receiver.paths() == ["/v1/traces"]


def test_signal_specific_endpoint_is_used_verbatim(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9/never")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", f"{http_receiver.endpoint}/ingest/v1/traces")
    setup_tracing(service_name="svc-specific")
    _emit()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    assert http_receiver.paths() == ["/ingest/v1/traces"]


def test_grpc_protocol_reaches_a_grpc_collector(grpc_receiver: OtlpGrpcReceiver) -> None:
    setup_tracing(service_name="svc-grpc", otlp_endpoint=grpc_receiver.endpoint, otlp_protocol="grpc")
    _emit()

    assert grpc_receiver.wait_for(lambda: bool(grpc_receiver.spans()))
    assert grpc_receiver.spans()[0].resource["service.name"] == "svc-grpc"
    assert get_telemetry_posture()["exporter_type"] == "otlp_grpc"


def test_protocol_selected_by_the_standard_environment(
    grpc_receiver: OtlpGrpcReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", grpc_receiver.endpoint)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    setup_tracing()
    _emit()

    assert grpc_receiver.wait_for(lambda: bool(grpc_receiver.spans()))


def test_headers_are_delivered_over_http(http_receiver: OtlpHttpReceiver) -> None:
    setup_tracing(otlp_endpoint=http_receiver.endpoint, otlp_headers="x-api-key=abc123,x-tenant=t%201")
    _emit()

    assert http_receiver.wait_for(lambda: bool(http_receiver.requests))
    headers = http_receiver.requests[0].headers
    assert headers["x-api-key"] == "abc123"
    assert headers["x-tenant"] == "t 1"


def test_headers_from_the_environment_are_delivered_over_grpc(
    grpc_receiver: OtlpGrpcReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-api-key=from-env")
    setup_tracing(otlp_endpoint=grpc_receiver.endpoint, otlp_protocol="grpc")
    _emit()

    assert grpc_receiver.wait_for(lambda: bool(grpc_receiver.requests))
    assert grpc_receiver.requests[0].headers["x-api-key"] == "from-env"


def test_resource_defaults_yield_to_the_standard_environment(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment.name=prod,team=agents")
    setup_tracing(
        service_name="default-name",
        otlp_endpoint=http_receiver.endpoint,
        resource_attributes={"service.version": "1.2.3", "deployment.environment.name": "dev"},
    )
    _emit()

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    resource = http_receiver.spans()[0].resource
    assert resource["service.name"] == "from-env"
    assert resource["service.version"] == "1.2.3"
    assert resource["deployment.environment.name"] == "prod"
    assert resource["team"] == "agents"


def test_nothing_is_installed_without_a_destination() -> None:
    setup_tracing(service_name="svc-off")

    assert not is_tracing_initialized()
    assert get_telemetry_posture()["status"] == "noop"


def test_the_kill_switch_wins_over_a_configured_endpoint(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    setup_tracing(otlp_endpoint=http_receiver.endpoint)

    assert not is_tracing_initialized()
    assert get_telemetry_posture()["status"] == "disabled"


def test_exporter_none_switches_the_environment_destination_off_but_not_an_explicit_one(
    http_receiver: OtlpHttpReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", http_receiver.endpoint)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    setup_tracing()
    assert not is_tracing_initialized()

    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    assert is_tracing_initialized()


def test_a_missing_http_exporter_degrades_visibly_and_never_swaps_protocol(
    http_receiver: OtlpHttpReceiver, grpc_receiver: OtlpGrpcReceiver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http.trace_exporter", None)
    setup_tracing(otlp_endpoint=http_receiver.endpoint)

    assert not is_tracing_initialized()
    posture = get_telemetry_posture()
    assert posture["status"] == "degraded"
    assert "http/protobuf" in str(posture["degraded_reason"])
    assert posture["exporter_type"] == "none"
    assert http_receiver.requests == []
    assert grpc_receiver.requests == []


def test_a_collector_that_rejects_batches_is_reported_as_failing() -> None:
    receiver = OtlpHttpReceiver(status=400)
    receiver.start()
    try:
        setup_tracing(otlp_endpoint=receiver.endpoint)
        with trace_context("tests.otlp", "rejected", {"agent.step": 1}):
            pass
        force_flush_tracing(timeout_ms=5000)

        assert receiver.wait_for(lambda: bool(receiver.requests))
        posture = get_telemetry_posture()
        assert posture["status"] == "failing"
        assert posture["failed_batches"] >= 1
        assert posture["last_failure_at"] is not None
        assert posture["exported_spans"] == 0
    finally:
        receiver.stop()


def test_a_healthy_collector_is_reported_active_with_counters(http_receiver: OtlpHttpReceiver) -> None:
    setup_tracing(otlp_endpoint=http_receiver.endpoint)
    _emit("first")
    _emit("second")

    assert http_receiver.wait_for(lambda: len(http_receiver.spans()) == 2)
    posture = get_telemetry_posture()
    assert posture["status"] == "active"
    assert posture["exported_spans"] == 2
    assert posture["failed_batches"] == 0
    assert posture["last_success_at"] is not None
    assert posture["exporter_type"] == "otlp_http"
    assert (
        posture["sampler"]
        == "ParentBased{root:AlwaysOnSampler,remoteParentSampled:AlwaysOnSampler,remoteParentNotSampled:AlwaysOffSampler,localParentSampled:AlwaysOnSampler,localParentNotSampled:AlwaysOffSampler}"
    )


def test_a_malformed_endpoint_neither_breaks_setup_nor_the_posture() -> None:
    setup_tracing(otlp_endpoint="http://user:secretpass@[::1")
    posture = get_telemetry_posture()

    assert isinstance(posture["endpoint"], str)
    assert "secretpass" not in str(posture)


def test_the_posture_never_exposes_credentials(http_receiver: OtlpHttpReceiver) -> None:
    host_port = http_receiver.endpoint.removeprefix("http://")
    setup_tracing(otlp_endpoint=f"http://user:secretpass@{host_port}", otlp_headers="authorization=Bearer abc")
    posture = get_telemetry_posture()

    assert "secretpass" not in str(posture)
    assert "abc" not in str(posture)
    assert posture["headers_configured"] is True
