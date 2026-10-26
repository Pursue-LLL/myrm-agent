"""Monitoring & Observability Manager

Consolidates Prometheus metrics and OpenTelemetry (traces + metrics) initialization.
Both stay off unless explicitly enabled: Prometheus by ``METRICS_ENABLED``,
OpenTelemetry by configuring an OTLP endpoint through the standard ``OTEL_*`` variables.
Gateway runtime vitals export: `gateway_vitals_metrics.py` (updated on `/health/liveness`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config.settings import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_OTEL_SERVICE_NAME = "myrm-agent-server"


def is_metrics_enabled() -> bool:
    """Check if metrics are enabled based on settings and deploy mode."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    caps = get_deployment_capabilities()
    if settings.monitoring.metrics_enabled:
        return True

    return caps.default_metrics_enabled


def setup_monitoring(app: FastAPI) -> None:
    """Complete monitoring setup: OpenTelemetry export + Prometheus endpoint."""
    _setup_telemetry()

    if is_metrics_enabled():
        _setup_prometheus(app)
    else:
        logger.debug("[Monitoring] Metrics disabled for current deploy mode")


def _setup_telemetry() -> None:
    """Export OpenTelemetry traces and metrics when the standard ``OTEL_*`` environment configures it.

    Endpoint, protocol, headers, sampler and the ``OTEL_SDK_DISABLED`` kill switch are resolved by the
    harness from the standard variables; the server only names the service and what it runs as.
    """
    try:
        from myrm_agent_harness import __version__ as engine_version
        from myrm_agent_harness.infra.tracing import setup_metrics, setup_tracing

        from app.config.deploy_mode import get_deploy_mode

        resource_attributes = {
            "service.version": engine_version,
            "deployment.environment.name": get_deploy_mode().value,
        }
        setup_tracing(service_name=_OTEL_SERVICE_NAME, resource_attributes=resource_attributes)
        setup_metrics(service_name=_OTEL_SERVICE_NAME, resource_attributes=resource_attributes)
    except Exception as e:
        logger.warning("[Telemetry] Setup failed: %s", e)


def _setup_prometheus(app: FastAPI) -> None:
    """Setup Prometheus metrics endpoints and collectors."""
    try:
        from fastapi import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        from app.core.monitoring.prometheus_setup import setup_http_metrics

        setup_http_metrics(app)

        @app.get("/metrics", include_in_schema=False)
        def metrics_endpoint() -> Response:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        logger.info("[Metrics] Prometheus endpoint enabled (/metrics)")
    except Exception as e:
        logger.warning("[Metrics] Setup failed: %s", e)


async def register_db_pool_metrics() -> None:
    """Start DB pool metrics collection if enabled."""
    if not is_metrics_enabled():
        return

    try:
        from myrm_agent_harness.observability.metrics.db_pool_collector import (
            DatabasePoolCollector,
        )
        from prometheus_client import REGISTRY

        from app.platform_utils import get_database_engine

        names = [
            "myrm_db_pool_size",
            "myrm_db_pool_checked_in",
            "myrm_db_pool_checked_out",
        ]
        for collector in list(REGISTRY._collector_to_names.keys()):
            if any(name in REGISTRY._collector_to_names[collector] for name in names):
                REGISTRY.unregister(collector)

        engine = get_database_engine()
        collector = DatabasePoolCollector(engine.sync_engine, "async")
        REGISTRY.register(collector)
        logger.info("[Metrics] Database Pool collector registered")
    except Exception as e:
        logger.debug("[Metrics] DB Pool collector registration skipped: %s", e)
