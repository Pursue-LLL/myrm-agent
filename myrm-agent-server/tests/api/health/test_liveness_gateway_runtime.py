"""Tests for gatewayRuntime vitals on GET /api/v1/health/liveness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from myrm_agent_harness.observability.diagnostics.gateway_health import (
    GatewayHealthStatus,
    GatewayRedactedHealthDTO,
    GatewayVitals,
)

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")

_HEALTHY_DTO = GatewayRedactedHealthDTO(
    status=GatewayHealthStatus.HEALTHY,
    vitals=GatewayVitals(2.0, 128.0, 60.0, 3),
    otlp_endpoint_configured=False,
    otlp_connected=False,
    redacted_diagnostics=("Gateway vitals nominal.",),
)

_DEGRADED_DTO = GatewayRedactedHealthDTO(
    status=GatewayHealthStatus.DEGRADED,
    vitals=GatewayVitals(350.0, 512.0, 60.0, 12),
    otlp_endpoint_configured=True,
    otlp_connected=False,
    redacted_diagnostics=("Elevated event loop lag.",),
)


def _mock_agent_gateway() -> MagicMock:
    mock_agent_gateway = MagicMock()
    mock_agent_gateway.get_active_sessions.return_value = []
    mock_agent_gateway.active_count = 0
    mock_agent_gateway.config.max_per_user = 4
    mock_agent_gateway.get_available_slots.return_value = 4
    mock_agent_gateway.is_draining = False
    return mock_agent_gateway


def test_liveness_includes_gateway_runtime_block() -> None:
    mock_bus = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=0)
    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus
    mock_gateway.get_status.return_value = {}

    with (
        patch("app.api.health.liveness.get_agent_gateway", return_value=_mock_agent_gateway()),
        patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway),
        patch(
            "app.api.health.liveness._build_memory_summary",
            return_value={"level": "unknown", "percent": 0.0},
        ),
        patch(
            "myrm_agent_harness.observability.diagnostics.gateway_health.GatewayHealthInspector.inspect",
            AsyncMock(return_value=_HEALTHY_DTO),
        ),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/health/liveness")

    assert response.status_code == 200
    body = response.json()
    assert "gatewayRuntime" in body
    assert body["gatewayRuntime"]["status"] == "HEALTHY"
    assert body["gatewayRuntime"]["vitals"]["event_loop_lag_ms"] == 2.0
    assert body["state"] == "idle"


def test_liveness_marks_degraded_when_gateway_runtime_unhealthy() -> None:
    mock_bus = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=0)
    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus
    mock_gateway.get_status.return_value = {}

    with (
        patch("app.api.health.liveness.get_agent_gateway", return_value=_mock_agent_gateway()),
        patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway),
        patch(
            "app.api.health.liveness._build_memory_summary",
            return_value={"level": "unknown", "percent": 0.0},
        ),
        patch(
            "myrm_agent_harness.observability.diagnostics.gateway_health.GatewayHealthInspector.inspect",
            AsyncMock(return_value=_DEGRADED_DTO),
        ),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/health/liveness")

    assert response.status_code == 200
    body = response.json()
    assert body["gatewayRuntime"]["status"] == "DEGRADED"
    assert body["state"] == "degraded"


def test_record_gateway_vitals_updates_prometheus_gauges() -> None:
    from prometheus_client import generate_latest

    from app.core.monitoring.gateway_vitals_metrics import record_gateway_vitals

    record_gateway_vitals(_DEGRADED_DTO)
    metrics_text = generate_latest().decode("utf-8")

    assert "myrm_gateway_event_loop_lag_ms 350.0" in metrics_text
    assert "myrm_gateway_health_status_code 1.0" in metrics_text
