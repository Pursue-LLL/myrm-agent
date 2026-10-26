"""Metrics provider setup on the same OTLP pipeline as tracing.

Design:
- Framework instruments (``get_meter``) are NoOp until ``setup_metrics`` installs a MeterProvider.
- The exporter comes from the shared OTLP factory, so protocol, endpoint and header semantics match
  the trace pipeline: one ``OTEL_EXPORTER_OTLP_ENDPOINT`` serves both signals, and
  ``OTEL_METRICS_EXPORTER=none`` switches metrics off on their own.
- No HTTP server is started here; Prometheus scraping stays a business-layer decision.

[INPUT]
- opentelemetry.sdk.metrics (POS: Metrics SDK, optional extra)
- infra.tracing.otlp (POS: target resolution, official exporters, resource, posture)

[OUTPUT]
- setup_metrics: initialize metric export (called by the business layer)
- is_metrics_initialized / get_meter_provider: live state
- force_flush_metrics / shutdown_metrics: bounded lifecycle

[POS]
Metrics exporter configuration. Pushes to an OTLP endpoint (HTTP/protobuf or gRPC) or, for
development, to the console.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.tracing.otlp.config import (
    apply_local_isolation,
    redact_endpoint,
    resolve_target,
    sdk_disabled,
)
from myrm_agent_harness.infra.tracing.otlp.lifecycle import run_bounded
from myrm_agent_harness.infra.tracing.otlp.posture import record_metrics, reset_metrics

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics import MeterProvider

HAS_OTEL_SDK = importlib.util.find_spec("opentelemetry.sdk") is not None

logger = logging.getLogger(__name__)

_meter_provider: MeterProvider | None = None
_initialized = False


def setup_metrics(
    service_name: str = "myrm-agent-harness",
    console_export: bool = False,
    export_interval_ms: int | None = None,
    otlp_endpoint: str | None = None,
    otlp_headers: dict[str, str] | str | None = None,
    otlp_protocol: str | None = None,
    local_trace_only: bool = False,
    resource_attributes: Mapping[str, str] | None = None,
) -> None:
    """Initialize metric export.

    This is a convenience function intended for the business layer. The framework never calls it
    automatically; without a MeterProvider every instrument is a NoOp.

    Args:
        service_name: Default ``service.name`` (``OTEL_SERVICE_NAME`` wins when set).
        console_export: Print metrics to stdout (development). Ignored when an OTLP endpoint is set.
        export_interval_ms: Push interval; default is ``OTEL_METRIC_EXPORT_INTERVAL`` or 60 s.
        otlp_endpoint / otlp_headers / otlp_protocol: Explicit target; otherwise ``OTEL_EXPORTER_OTLP_*``.
        local_trace_only: Refuse remote export (also enforced by ``MYRM_LOCAL_TRACE_ONLY``).
        resource_attributes: Default resource attributes (``OTEL_RESOURCE_ATTRIBUTES`` wins).

    A requested protocol that cannot be served leaves metrics off; it never falls back to another
    protocol or to stdout.
    """
    global _meter_provider, _initialized

    target = apply_local_isolation(
        resolve_target("metrics", endpoint=otlp_endpoint, protocol=otlp_protocol, headers=otlp_headers),
        requested=local_trace_only,
    )
    if not HAS_OTEL_SDK:
        logger.warning("OpenTelemetry SDK not installed. Metrics run in NoOp mode. Install the `observability` extra.")
        return
    if sdk_disabled():
        logger.info("OTEL_SDK_DISABLED is set: metrics stay off")
        return
    if _initialized:
        logger.debug("Metrics already initialized")
        return
    if target is None and not console_export:
        logger.debug("No OTLP endpoint configured: metrics stay off")
        return

    from opentelemetry.metrics import get_meter_provider as current_meter_provider
    from opentelemetry.metrics import set_meter_provider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

    from myrm_agent_harness.infra.tracing.otlp.exporters import OtlpUnavailableError, create_metric_exporter
    from myrm_agent_harness.infra.tracing.otlp.resource import build_resource

    if target is not None:
        try:
            exporter = create_metric_exporter(target)
        except OtlpUnavailableError as exc:
            logger.warning("OTLP metric export unavailable, metrics stay off: %s", exc)
            return
    else:
        exporter = ConsoleMetricExporter()

    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=export_interval_ms)
    provider = MeterProvider(resource=build_resource(service_name, resource_attributes), metric_readers=[reader])
    set_meter_provider(provider)
    if current_meter_provider() is not provider:
        provider.shutdown()
        logger.warning("Metrics not installed: another MeterProvider is already installed in this process")
        return

    _meter_provider = provider
    _initialized = True
    record_metrics(exporting=True)
    logger.info(
        "Metrics initialized: service=%s endpoint=%s",
        service_name,
        redact_endpoint(target.endpoint) if target else "stdout",
    )


def is_metrics_initialized() -> bool:
    """Return True when ``setup_metrics()`` has configured a real MeterProvider."""
    return _initialized


def get_meter_provider() -> MeterProvider | None:
    """Return the MeterProvider installed by ``setup_metrics()``, or None."""
    return _meter_provider


def force_flush_metrics(timeout_ms: float = 1500.0) -> bool:
    """Flush buffered metrics with a deadline; False when uninitialized, late or failed."""
    if not _initialized or _meter_provider is None:
        return False
    return run_bounded(
        _meter_provider.force_flush,
        thread_name="otel-metrics-bounded-flush",
        timeout_ms=timeout_ms,
        label="metrics force_flush",
    )


def shutdown_metrics(timeout_ms: float = 1500.0) -> bool:
    """Shut the meter provider down with a deadline so a hung collector cannot block process exit."""
    global _meter_provider, _initialized

    if not _initialized or _meter_provider is None:
        return False
    provider = _meter_provider
    _meter_provider = None
    _initialized = False
    reset_metrics()
    done = run_bounded(
        provider.shutdown,
        thread_name="otel-metrics-bounded-shutdown",
        timeout_ms=timeout_ms,
        label="metrics provider shutdown",
    )
    if done:
        logger.info("Metrics provider shutdown complete")
    return done
