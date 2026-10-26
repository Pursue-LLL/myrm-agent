"""Endpoint resolution follows the OpenTelemetry spec; the zero-egress gate parses hosts instead of prefixes."""

from __future__ import annotations

import pytest

from myrm_agent_harness.infra.tracing.otlp.config import (
    apply_local_isolation,
    assert_local_trace_only,
    configured_endpoints,
    is_local_endpoint,
    parse_otlp_headers,
    redact_endpoint,
    resolve_target,
    sdk_disabled,
)

_OTLP_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_SDK_DISABLED",
    "MYRM_LOCAL_TRACE_ONLY",
)


@pytest.fixture(autouse=True)
def _clean_otlp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _OTLP_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_no_endpoint_means_no_target() -> None:
    assert resolve_target("traces") is None
    assert resolve_target("metrics") is None


@pytest.mark.parametrize(
    ("signal", "expected"),
    [("traces", "http://collector:4318/v1/traces"), ("metrics", "http://collector:4318/v1/metrics")],
)
def test_a_base_url_gets_the_signal_path_for_http(signal: str, expected: str) -> None:
    target = resolve_target(signal, endpoint="http://collector:4318")  # type: ignore[arg-type]

    assert target is not None
    assert (target.endpoint, target.protocol) == (expected, "http/protobuf")


def test_a_base_url_that_already_names_the_path_is_not_doubled() -> None:
    target = resolve_target("traces", endpoint="http://collector:4318/v1/traces/")

    assert target is not None and target.endpoint == "http://collector:4318/v1/traces"


def test_grpc_takes_the_endpoint_as_given() -> None:
    target = resolve_target("traces", endpoint="http://collector:4317", protocol="grpc")

    assert target is not None
    assert (target.endpoint, target.protocol) == ("http://collector:4317", "grpc")


def test_a_signal_specific_variable_is_used_verbatim_and_precedes_the_general_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://general:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://special:4318/custom")

    traces, metrics = resolve_target("traces"), resolve_target("metrics")

    assert traces is not None and traces.endpoint == "http://special:4318/custom"
    assert metrics is not None and metrics.endpoint == "http://general:4318/v1/metrics"


def test_an_explicit_endpoint_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://env:4318")

    target = resolve_target("traces", endpoint="http://explicit:4318")

    assert target is not None and target.endpoint == "http://explicit:4318/v1/traces"


def test_protocol_precedence_is_argument_then_signal_then_general_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://c:4317")
    assert resolve_target("traces").protocol == "http/protobuf"  # type: ignore[union-attr]

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    assert resolve_target("traces").protocol == "grpc"  # type: ignore[union-attr]

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
    assert resolve_target("traces").protocol == "http/protobuf"  # type: ignore[union-attr]
    assert resolve_target("metrics").protocol == "grpc"  # type: ignore[union-attr]

    assert resolve_target("traces", protocol="GRPC").protocol == "grpc"  # type: ignore[union-attr]


def test_exporter_none_switches_an_environment_destination_off_per_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://c:4318")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")

    assert resolve_target("traces") is not None
    assert resolve_target("metrics") is None


def test_exporter_none_does_not_override_an_explicit_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")

    assert resolve_target("traces", endpoint="http://c:4318") is not None


def test_headers_are_reported_as_configured_without_leaking_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://c:4318")
    assert resolve_target("traces").headers_configured is False  # type: ignore[union-attr]

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20secret")
    from_env = resolve_target("traces")
    assert from_env is not None and from_env.headers_configured is True and from_env.headers is None

    explicit = resolve_target("traces", headers="X-Token=abc")
    assert explicit is not None and explicit.headers == {"X-Token": "abc"}


def test_header_lists_are_url_decoded_and_malformed_parts_ignored() -> None:
    assert parse_otlp_headers("a%20b=c%2Cd, e = f ,broken,=novalue") == {"a b": "c,d", "e": "f"}
    assert parse_otlp_headers("") == {}


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:4318",
        "localhost:4317",
        "http://127.0.0.1:4318/v1/traces",
        "http://[::1]:4318",
        "http://LOCALHOST:4318",
    ],
)
def test_loopback_hosts_are_local(endpoint: str) -> None:
    assert is_local_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost.attacker.example:4318",
        "http://localhost@attacker.example",
        "http://127.0.0.1.attacker.example",
        "https://collector.internal:4318",
        "http://10.0.0.5:4318",
        "http://[::ffff:10.0.0.5]:4318",
        "",
        "http://[invalid",
    ],
)
def test_lookalike_and_remote_hosts_are_not_local(endpoint: str) -> None:
    assert not is_local_endpoint(endpoint)


def test_credentials_are_removed_from_displayed_endpoints() -> None:
    shown = redact_endpoint("http://user:hunter2@collector.internal:4318/v1/traces")

    assert "hunter2" not in shown and "user:" not in shown
    assert "collector.internal:4318/v1/traces" in shown
    assert redact_endpoint("http://collector:4318") == "http://collector:4318"


@pytest.mark.parametrize(
    "endpoint",
    ["http://[::1", "http://user:hunter2@host:notaport/x", "http://user:hunter2@[::1", "user:hunter2@collector:4318"],
)
def test_a_malformed_endpoint_is_displayed_redacted_instead_of_raising(endpoint: str) -> None:
    assert "hunter2" not in redact_endpoint(endpoint)


def test_the_policy_variable_refuses_remote_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_local_trace_only("http://collector.internal:4318")  # policy off: permitted

    monkeypatch.setenv("MYRM_LOCAL_TRACE_ONLY", "true")
    assert_local_trace_only("http://127.0.0.1:4318")
    with pytest.raises(PermissionError) as refused:
        assert_local_trace_only("http://user:hunter2@collector.internal:4318")

    assert "hunter2" not in str(refused.value)


def test_a_caller_requested_local_mode_drops_remote_targets_quietly(caplog: pytest.LogCaptureFixture) -> None:
    remote = resolve_target("traces", endpoint="http://collector.internal:4318")
    local = resolve_target("traces", endpoint="http://127.0.0.1:4318")

    assert apply_local_isolation(remote, requested=True) is None
    assert apply_local_isolation(local, requested=True) is local
    assert apply_local_isolation(remote, requested=False) is remote
    assert apply_local_isolation(None, requested=True) is None
    assert "ignoring remote OTLP traces endpoint" in caplog.text


def test_the_operator_policy_overrides_a_caller_that_did_not_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_LOCAL_TRACE_ONLY", "1")
    remote = resolve_target("metrics", endpoint="http://collector.internal:4318")

    with pytest.raises(PermissionError):
        apply_local_isolation(remote, requested=False)


def test_the_audit_lists_every_configured_endpoint_even_when_its_signal_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://general:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://metrics:4318/m")

    assert configured_endpoints() == ["http://general:4318", "http://metrics:4318/m"]


@pytest.mark.parametrize(("value", "disabled"), [("true", True), ("TRUE", True), ("false", False), ("", False)])
def test_the_standard_kill_switch(monkeypatch: pytest.MonkeyPatch, value: str, disabled: bool) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", value)

    assert sdk_disabled() is disabled
