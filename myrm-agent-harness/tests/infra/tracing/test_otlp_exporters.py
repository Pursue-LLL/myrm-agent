"""The exporter factory's failures never quote the credentials the exporter was given.

The error text reaches the log, the telemetry posture API and the settings page, so it has to pass
the same redaction as the endpoint shown next to it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.infra.tracing.otlp import exporters
from myrm_agent_harness.infra.tracing.otlp.config import PROTOCOL_HTTP, OtlpTarget

_HEADER_SECRET = "Bearer s3cr3t-token-value"
_URL_PASSWORD = "p4ssw0rd-in-the-url"


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
