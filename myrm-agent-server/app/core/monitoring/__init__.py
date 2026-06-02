"""Monitoring & Observability Manager

Consolidates all metrics (Prometheus) and tracing (OpenTelemetry) initialization.
Ensures zero overhead in local/sandbox modes unless explicitly enabled.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config.settings import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def is_metrics_enabled() -> bool:
    """Check if metrics are enabled based on settings and deploy mode."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    caps = get_deployment_capabilities()
    if settings.monitoring.metrics_enabled:
        return True

    return caps.default_metrics_enabled


def setup_monitoring(app: FastAPI) -> None:
    """Complete monitoring setup: Tracing + Metrics."""
    _setup_tracing()

    if is_metrics_enabled():
        _setup_metrics(app)
    else:
        logger.debug("[Monitoring] Metrics disabled for current deploy mode")


def _setup_tracing() -> None:
    """Setup OpenTelemetry tracing via harness framework."""
    if not settings.monitoring.otel_enabled:
        return

    try:
        from myrm_agent_harness.infra.tracing import setup_tracing

        otlp_endpoint = settings.monitoring.otel_exporter_otlp_endpoint.strip()
        sample_rate = settings.monitoring.otel_sample_rate
        console_export = not otlp_endpoint

        setup_tracing(
            service_name="myrm-agent-server",
            console_export=console_export,
            sample_rate=sample_rate,
            otlp_endpoint=otlp_endpoint or None,
        )
        logger.info(
            "[Tracing] OpenTelemetry enabled (endpoint=%s, sample_rate=%.1f)",
            otlp_endpoint or "console",
            sample_rate,
        )
    except Exception as e:
        logger.warning("[Tracing] Setup failed: %s", e)


def _setup_metrics(app: FastAPI) -> None:
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
        from myrm_agent_harness.observability.metrics.db_pool_collector import DatabasePoolCollector
        from prometheus_client import REGISTRY

        from app.platform_utils import get_database_engine

        names = ["myrm_db_pool_size", "myrm_db_pool_checked_in", "myrm_db_pool_checked_out"]
        for collector in list(REGISTRY._collector_to_names.keys()):
            if any(name in REGISTRY._collector_to_names[collector] for name in names):
                REGISTRY.unregister(collector)

        engine = get_database_engine()
        collector = DatabasePoolCollector(engine, "async")
        REGISTRY.register(collector)
        logger.info("[Metrics] Database Pool collector registered")
    except Exception as e:
        logger.debug("[Metrics] DB Pool collector registration skipped: %s", e)
