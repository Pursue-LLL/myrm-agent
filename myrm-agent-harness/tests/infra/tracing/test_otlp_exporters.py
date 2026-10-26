"""The exporter factory never quotes the credentials the exporter was given or configured with.

The error text reaches the log, the telemetry posture API and the settings page, so it has to pass
the same redaction as the endpoint shown next to it. A malformed entry of the OTLP header variables
is a credential as well, and the stock exporters would quote it in a warning.
"""

from __future__ import annotations

import logging

import pytest

from myrm_agent_harness.infra.tracing.otlp import exporters
from myrm_agent_harness.infra.tracing.otlp.config import PROTOCOL_GRPC, PROTOCOL_HTTP, OtlpTarget, resolve_target

_HEADER_SECRET = "Bearer s3cr3t-token-value"
_URL_PASSWORD = "p4ssw0rd-in-the-url"
_HEADER_PARSER_LOGGER = "opentelemetry.util.re"
_VENDOR_TOKEN = "hcaik_01abcdef1234567890xyz"


class _ExporterThatEchoesItsArguments:
    """Stands in for an official exporter whose constructor quotes what it was handed."""

    def __init__(self, *, endpoint: str, headers: dict[str, str]) -> None:
        raise ValueError(f"cannot reach {endpoint} with authorization {headers['authorization']}")


def _target(headers: dict[str, str] | None) -> OtlpTarget:
    return OtlpTarget(
        signal="traces",
        endpoint=f"https://collector-user:{_URL_PASSWORD}@collector.example/v1/traces",
        protocol=PROTOCOL_HTTP,
        headers=headers,
        headers_configured=headers is not None,
    )


def test_a_constructor_failure_does_not_echo_the_header_value_or_the_url_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(exporters._LOADERS, ("traces", PROTOCOL_HTTP), lambda: _ExporterThatEchoesItsArguments)

    with pytest.raises(exporters.OtlpUnavailableError) as raised:
        exporters.create_span_exporter(_target({"authorization": _HEADER_SECRET}))

    message = str(raised.value)
    assert "could not be created" in message
    assert "collector.example" in message
    assert _HEADER_SECRET not in message
    assert _URL_PASSWORD not in message


def test_a_constructor_failure_without_headers_still_hides_the_url_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EchoesTheEndpoint:
        def __init__(self, *, endpoint: str) -> None:
            raise ValueError(f"invalid target {endpoint}")

    monkeypatch.setitem(exporters._LOADERS, ("traces", PROTOCOL_HTTP), lambda: _EchoesTheEndpoint)

    with pytest.raises(exporters.OtlpUnavailableError) as raised:
        exporters.create_span_exporter(_target(None))

    assert _URL_PASSWORD not in str(raised.value)


@pytest.mark.parametrize(
    ("signal", "protocol", "endpoint"),
    [
        ("traces", PROTOCOL_HTTP, "http://127.0.0.1:4318"),
        ("traces", PROTOCOL_GRPC, "http://127.0.0.1:4317"),
        ("metrics", PROTOCOL_HTTP, "http://127.0.0.1:4318"),
        ("metrics", PROTOCOL_GRPC, "http://127.0.0.1:4317"),
    ],
)
def test_a_malformed_header_entry_is_reported_without_its_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    signal: exporters.Signal,
    protocol: str,
    endpoint: str,
) -> None:
    # The usual typo: a curl-style ``name: value`` entry has no ``=``, so the stock parser rejects it.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", f"x-honeycomb-team: {_VENDOR_TOKEN}")
    target = resolve_target(signal, endpoint=endpoint, protocol=protocol)
    assert target is not None
    create = exporters.create_span_exporter if signal == "traces" else exporters.create_metric_exporter

    with caplog.at_level(logging.WARNING, logger=_HEADER_PARSER_LOGGER):
        exporter = create(target)
    exporter.shutdown()

    assert [record for record in caplog.records if record.name == _HEADER_PARSER_LOGGER], (
        "the operator is still told that an entry was ignored"
    )
    assert _VENDOR_TOKEN not in caplog.text


def test_well_formed_header_entries_stay_silent(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", f"authorization=Bearer%20{_VENDOR_TOKEN},x-tenant=acme")
    target = resolve_target("traces", endpoint="http://127.0.0.1:4318", protocol=PROTOCOL_HTTP)
    assert target is not None

    with caplog.at_level(logging.WARNING, logger=_HEADER_PARSER_LOGGER):
        exporters.create_span_exporter(target).shutdown()

    assert [record for record in caplog.records if record.name == _HEADER_PARSER_LOGGER] == []
