"""Cron / kanban agent runs bypass AgentGateway; liveness must still report them as busy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.core.agent.run_activity import track_background_agent_run
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")


def _get_liveness(*, gateway_active_count: int) -> dict[str, object]:
    mock_bus = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=0)
    mock_channel_gateway = MagicMock()
    mock_channel_gateway.bus = mock_bus
    mock_channel_gateway.get_status.return_value = {}

    mock_agent_gateway = MagicMock()
    mock_agent_gateway.get_active_sessions.return_value = []
    mock_agent_gateway.active_count = gateway_active_count
    mock_agent_gateway.config.max_per_user = 4
    mock_agent_gateway.get_available_slots.return_value = 4
    mock_agent_gateway.is_draining = False

    with (
        patch("app.api.health.liveness.get_agent_gateway", return_value=mock_agent_gateway),
        patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_channel_gateway),
        patch(
            "app.api.health.liveness._build_memory_summary",
            return_value={"level": "unknown", "percent": 0.0},
        ),
    ):
        response = TestClient(app).get("/api/v1/health/liveness")

    assert response.status_code == 200
    return response.json()


def test_liveness_idle_without_any_run() -> None:
    body = _get_liveness(gateway_active_count=0)

    assert body["state"] == "idle"
    assert body["agents"]["backgroundRunCount"] == 0


def test_liveness_busy_while_background_agent_run_in_flight() -> None:
    with track_background_agent_run():
        body = _get_liveness(gateway_active_count=0)

    assert body["state"] == "busy"
    assert body["agents"]["activeCount"] == 0
    assert body["agents"]["backgroundRunCount"] == 1
