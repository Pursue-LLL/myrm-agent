"""Official OTLP exporters for traces and metrics, selected by the requested protocol.

[INPUT]
- otlp.config::OtlpTarget (POS: resolved endpoint, protocol and headers)
- otlp.stats::ExportStats (POS: measured export outcome read by the posture probe)
- opentelemetry-exporter-otlp-proto-http / -grpc (POS: optional official exporters)

[OUTPUT]
- OtlpUnavailableError: the requested protocol cannot be served (package missing, unsupported, bad config);
  its message never quotes the target's credentials
- create_span_exporter / create_metric_exporter: exporter for one resolved target; a malformed entry of the
  OTLP header variables is reported without its text
- DeliveryTrackingMetricExporter: wraps a metric exporter and records whether each export was accepted

[POS]
One factory for both signals so traces and metrics share protocol, endpoint and header handling.
A request that cannot be honoured raises ``OtlpUnavailableError``; the caller degrades visibly. The
factory never substitutes another protocol or a console exporter, because a silent swap would
point telemetry at an endpoint that does not speak that protocol. The exporter packages are
imported literally (inside small loaders) so a frozen desktop bundle collects them and a missing
optional package surfaces as ``ImportError`` only when its protocol is requested. The stock exporters
read ``OTEL_EXPORTER_OTLP_*HEADERS`` from the environment themselves and, for a malformed entry, log
the entry verbatim; an entry is a credential, so that warning's text is replaced. The SDK's periodic metric
reader discards the result of every export, so the tracking wrapper is the only place a refused metric batch
can be observed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData
from opentelemetry.sdk.trace.export import SpanExporter

from myrm_agent_harness.infra.tracing.otlp.config import (
    PROTOCOL_GRPC,
    PROTOCOL_HTTP,
    OtlpTarget,
    Signal,
    redact_endpoint,
)
from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats

logger = logging.getLogger(__name__)

_PACKAGE_FLAVOR: dict[str, str] = {
    PROTOCOL_HTTP: "http",
    PROTOCOL_GRPC: "grpc",
}

# The logger the SDK's header parser warns through (``opentelemetry.util.re``).
_HEADER_PARSER_LOGGER = "opentelemetry.util.re"


class OtlpUnavailableError(Exception):
    """The requested OTLP protocol cannot be served by this installation or configuration."""


class _WithholdHeaderEntry(logging.Filter):
    """Replace the header parser's warning text, which quotes the malformed entry verbatim."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "An entry of the OTLP headers is malformed and is ignored (its text is withheld)."
        record.args = None
        return True


def _withhold_header_text() -> None:
    """Install the filter once per process, before an exporter reads the header variables."""
    parser_logger = logging.getLogger(_HEADER_PARSER_LOGGER)
    if not any(isinstance(existing, _WithholdHeaderEntry) for existing in parser_logger.filters):
        parser_logger.addFilter(_WithholdHeaderEntry())


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
    _withhold_header_text()
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


class DeliveryTrackingMetricExporter(MetricExporter):
    """Wraps a metric exporter and records whether each export was accepted.

    Without it a collector that refuses metrics (Jaeger answers 404 on ``/v1/metrics``) would look healthy,
    because the periodic reader ignores the outcome of an export. Temporality and aggregation are the wrapped
    exporter's own: the reader takes both from the exporter it is given.
    """

    def __init__(self, inner: MetricExporter) -> None:
        super().__init__(
            preferred_temporality=inner._preferred_temporality,
            preferred_aggregation=inner._preferred_aggregation,
        )
        self._inner = inner
        self._lock = threading.Lock()
        self._stats = ExportStats()

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: object) -> MetricExportResult:
        try:
            result = self._inner.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
        except Exception as exc:
            logger.warning("OTLP metric export raised %s", type(exc).__name__)
            result = MetricExportResult.FAILURE
        self._record(result)
        return result

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._inner.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        self._inner.shutdown(timeout_millis=timeout_millis, **kwargs)

    def stats(self) -> ExportStats:
        with self._lock:
            return self._stats

    def _record(self, result: MetricExportResult) -> None:
        now = time.time()
        with self._lock:
            if result is MetricExportResult.SUCCESS:
                self._stats = replace(self._stats, last_success_at=now)
            else:
                self._stats = replace(self._stats, failed_batches=self._stats.failed_batches + 1, last_failure_at=now)
