"""Tests for graceful shutdown, drain APIs, and WAL checkpoint flush on shutdown."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.shutdown import graceful_shutdown_task


@pytest.fixture
def app() -> FastAPI:
    from tests.support.minimal_app import build_minimal_app

    return build_minimal_app(preset="system")


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_begin_drain_api(client: TestClient) -> None:
    """POST /api/v1/system/drain initiates draining and returns active count."""
    response = client.post("/api/v1/system/drain")
    assert response.status_code == 200
    data = response.json()
    assert data["draining"] is True
    assert "active_count" in data


def test_cancel_drain_api(client: TestClient) -> None:
    """DELETE /api/v1/system/drain cancels an active drain."""
    response = client.delete("/api/v1/system/drain")
    assert response.status_code == 200
    data = response.json()
    assert "draining" in data
    assert "was_draining" in data


def test_shutdown_endpoint(client: TestClient) -> None:
    """POST /api/v1/system/shutdown queues graceful shutdown background task."""
    response = client.post("/api/v1/system/shutdown")
    assert response.status_code == 200
    assert response.json()["status"] == "shutting_down"


@pytest.mark.asyncio
async def test_graceful_shutdown_task_flow() -> None:
    """Verifies that graceful_shutdown_task executes drain, WAL flush, and harness cleanup."""
    mock_gateway = MagicMock()
    mock_gateway.active_count = 0
    mock_gateway.begin_drain = AsyncMock()

    mock_conn = AsyncMock()
    mock_conn.exec_driver_sql = AsyncMock()

    class MockBeginCtx:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_engine = MagicMock()
    mock_engine.begin.return_value = MockBeginCtx()

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
        patch("app.platform_utils.get_database_engine", return_value=mock_engine),
        patch("app.lifecycle.harness_bridge.close_harness_resources", new_callable=AsyncMock) as mock_close,
        patch("os.kill") as mock_kill,
    ):
        await graceful_shutdown_task()

        mock_gateway.begin_drain.assert_awaited_once()
        mock_conn.exec_driver_sql.assert_awaited_with("PRAGMA wal_checkpoint(TRUNCATE)")
        mock_close.assert_awaited_once()
        mock_kill.assert_called_once()
