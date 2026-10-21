"""Prometheus gauges for gateway runtime vitals (event loop, RSS, asyncio tasks).

[INPUT]
- myrm_agent_harness.observability.diagnostics.gateway_health::GatewayRedactedHealthDTO (POS: zero-payload gateway health DTO)

[OUTPUT]
- record_gateway_vitals: Update Prometheus gauges from a gateway health inspection snapshot

[POS]
Server-layer Prometheus export for cloud monitoring scrapes on /metrics.
"""

from __future__ import annotations

from myrm_agent_harness.observability.diagnostics.gateway_health import (
    GatewayHealthStatus,
    GatewayRedactedHealthDTO,
)

try:
    from prometheus_client import Gauge

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    Gauge = None  # type: ignore

_STATUS_TO_CODE: dict[GatewayHealthStatus, int] = {
    GatewayHealthStatus.HEALTHY: 0,
    GatewayHealthStatus.DEGRADED: 1,
    GatewayHealthStatus.UNHEALTHY: 2,
}

if HAS_PROMETHEUS:
    GATEWAY_EVENT_LOOP_LAG_MS = Gauge(
        "myrm_gateway_event_loop_lag_ms",
        "Gateway asyncio event loop scheduling lag in milliseconds",
    )
    GATEWAY_PROCESS_RSS_MB = Gauge(
        "myrm_gateway_process_rss_mb",
        "Gateway process resident set size in megabytes",
    )
    GATEWAY_ACTIVE_ASYNCIO_TASKS = Gauge(
        "myrm_gateway_active_asyncio_tasks",
        "Active asyncio tasks in the gateway process",
    )
    GATEWAY_HEALTH_STATUS_CODE = Gauge(
        "myrm_gateway_health_status_code",
        "Gateway health status (0=HEALTHY, 1=DEGRADED, 2=UNHEALTHY)",
    )


def record_gateway_vitals(dto: GatewayRedactedHealthDTO) -> None:
    """Publish gateway vitals to Prometheus default registry."""
    if not HAS_PROMETHEUS:
        return

    GATEWAY_EVENT_LOOP_LAG_MS.set(dto.vitals.event_loop_lag_ms)
    GATEWAY_PROCESS_RSS_MB.set(dto.vitals.memory_rss_mb)
    GATEWAY_ACTIVE_ASYNCIO_TASKS.set(float(dto.vitals.active_tasks))
    GATEWAY_HEALTH_STATUS_CODE.set(float(_STATUS_TO_CODE.get(dto.status, 2)))
