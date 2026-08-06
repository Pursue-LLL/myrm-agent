"""Tests for GET /api/v1/health/liveness pendingOutboundCount field."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")


def test_liveness_includes_pending_outbound_count() -> None:
    mock_bus = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=3)
    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus
    mock_gateway.get_status.return_value = {}

    mock_agent_gateway = MagicMock()
    mock_agent_gateway.get_active_sessions.return_value = []
    mock_agent_gateway.active_count = 0
    mock_agent_gateway.config.max_per_user = 4
    mock_agent_gateway.get_available_slots.return_value = 4
    mock_agent_gateway.is_draining = False

    with (
        patch(
            "app.api.health.liveness.get_agent_gateway", return_value=mock_agent_gateway
        ),
        patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway),
        patch(
            "app.api.health.liveness._build_memory_summary",
            return_value={"level": "unknown", "percent": 0.0},
        ),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/health/liveness")

    assert response.status_code == 200
    body = response.json()
    assert body["pendingOutboundCount"] == 3
    assert body["state"] == "idle"
