"""Official OTLP exporters for traces and metrics, selected by the requested protocol.

[INPUT]
- otlp.config::OtlpTarget (POS: resolved endpoint, protocol and headers)
- opentelemetry-exporter-otlp-proto-http / -grpc (POS: optional official exporters)

[OUTPUT]
- OtlpUnavailableError: the requested protocol cannot be served (package missing, unsupported, bad config);
  its message never quotes the target's credentials
- create_span_exporter / create_metric_exporter: exporter for one resolved target

[POS]
One factory for both signals so traces and metrics share protocol, endpoint and header handling.
A request that cannot be honoured raises ``OtlpUnavailableError``; the caller degrades visibly. The
factory never substitutes another protocol or a console exporter, because a silent swap would
point telemetry at an endpoint that does not speak that protocol. The exporter packages are
imported literally (inside small loaders) so a frozen desktop bundle collects them and a missing
optional package surfaces as ``ImportError`` only when its protocol is requested.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from opentelemetry.sdk.metrics.export import MetricExporter
from opentelemetry.sdk.trace.export import SpanExporter

from myrm_agent_harness.infra.tracing.otlp.config import (
    PROTOCOL_GRPC,
    PROTOCOL_HTTP,
    OtlpTarget,
    Signal,
    redact_endpoint,
)

_PACKAGE_FLAVOR: dict[str, str] = {
    PROTOCOL_HTTP: "http",
    PROTOCOL_GRPC: "grpc",
}


class OtlpUnavailableError(Exception):
    """The requested OTLP protocol cannot be served by this installation or configuration."""


def _http_span_exporter() -> type:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter


def _grpc_span_exporter() -> type:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter


def _http_metric_exporter() -> type:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    return OTLPMetricExporter


def _grpc_metric_exporter() -> type:
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    return OTLPMetricExporter


_LOADERS: dict[tuple[Signal, str], Callable[[], type]] = {
    ("traces", PROTOCOL_HTTP): _http_span_exporter,
    ("traces", PROTOCOL_GRPC): _grpc_span_exporter,
    ("metrics", PROTOCOL_HTTP): _http_metric_exporter,
    ("metrics", PROTOCOL_GRPC): _grpc_metric_exporter,
}


def _exporter_class(target: OtlpTarget) -> type:
    loader = _LOADERS.get((target.signal, target.protocol))
    if loader is None:
        raise OtlpUnavailableError(
            f"Unsupported OTLP protocol '{target.protocol}'; use '{PROTOCOL_HTTP}' or '{PROTOCOL_GRPC}'."
        )
    try:
        return loader()
    except ImportError as exc:
        raise OtlpUnavailableError(
            f"OTLP protocol '{target.protocol}' needs the "
            f"opentelemetry-exporter-otlp-proto-{_PACKAGE_FLAVOR[target.protocol]} package ({exc})."
        ) from exc


def _scrub(message: str, target: OtlpTarget) -> str:
    """Mask the target's credentials in text that may quote what the exporter was given."""
    for value in (target.headers or {}).values():
        if value:
            message = message.replace(value, "[REDACTED]")
    return redact_endpoint(message)


def _build(target: OtlpTarget) -> object:
    exporter_class = _exporter_class(target)
    kwargs: dict[str, object] = {"endpoint": target.endpoint}
    if target.headers is not None:
        kwargs["headers"] = target.headers
    try:
        return exporter_class(**kwargs)
    except Exception as exc:
        raise OtlpUnavailableError(
            f"OTLP {target.signal} exporter could not be created: {_scrub(str(exc), target)}"
        ) from exc


def create_span_exporter(target: OtlpTarget) -> SpanExporter:
    return cast(SpanExporter, _build(target))


def create_metric_exporter(target: OtlpTarget) -> MetricExporter:
    return cast(MetricExporter, _build(target))
