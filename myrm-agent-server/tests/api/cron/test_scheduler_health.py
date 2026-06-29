"""Unit tests for GET /cron/scheduler/health endpoint.

Validates status classification logic across all edge cases:
- green: running + recent tick + no errors
- yellow: running + startup (no tick yet, has timer)
- yellow: running + stale tick (>120s) or tick_errors > 0
- red: not running
- red: running + no tick + no timer
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app() -> Generator[FastAPI, None, None]:
    from app.api.cron.routes import helpers
    from app.api.cron.routes.scheduler_health import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/cron")

    mock_scheduler = MagicMock()
    with patch.object(helpers, "_get_scheduler", return_value=mock_scheduler):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def mock_scheduler(app: FastAPI) -> MagicMock:
    from app.api.cron.routes import helpers

    return helpers._get_scheduler()


class TestSchedulerHealthGreen:
    """Status = green when scheduler is running, recent tick, no errors."""

    def test_healthy_scheduler(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        now = datetime.now(UTC)
        mock_scheduler.health.return_value = {
            "running": True,
            "last_tick_at": now.isoformat(),
            "tick_errors": 0,
            "has_timer": True,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "green"
        assert data["running"] is True
        assert data["tick_errors"] == 0
        assert data["has_timer"] is True
        assert data["last_tick_age_seconds"] is not None
        assert data["last_tick_age_seconds"] < 5


class TestSchedulerHealthYellow:
    """Status = yellow for degraded conditions."""

    def test_startup_phase_with_timer(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        mock_scheduler.health.return_value = {
            "running": True,
            "last_tick_at": None,
            "tick_errors": 0,
            "has_timer": True,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        data = resp.json()

        assert data["status"] == "yellow"
        assert data["running"] is True
        assert data["last_tick_at"] is None

    def test_stale_tick(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        stale = datetime.now(UTC) - timedelta(seconds=200)
        mock_scheduler.health.return_value = {
            "running": True,
            "last_tick_at": stale.isoformat(),
            "tick_errors": 0,
            "has_timer": True,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        data = resp.json()

        assert data["status"] == "yellow"
        assert data["last_tick_age_seconds"] is not None
        assert data["last_tick_age_seconds"] > 120

    def test_tick_errors(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        now = datetime.now(UTC)
        mock_scheduler.health.return_value = {
            "running": True,
            "last_tick_at": now.isoformat(),
            "tick_errors": 3,
            "has_timer": True,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        data = resp.json()

        assert data["status"] == "yellow"
        assert data["tick_errors"] == 3


class TestSchedulerHealthRed:
    """Status = red for critical failures."""

    def test_not_running(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        mock_scheduler.health.return_value = {
            "running": False,
            "last_tick_at": None,
            "tick_errors": 0,
            "has_timer": False,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        data = resp.json()

        assert data["status"] == "red"
        assert data["running"] is False

    def test_running_no_tick_no_timer(self, client: TestClient, mock_scheduler: MagicMock) -> None:
        mock_scheduler.health.return_value = {
            "running": True,
            "last_tick_at": None,
            "tick_errors": 0,
            "has_timer": False,
            "last_purge_at": None,
        }

        resp = client.get("/cron/scheduler/health")
        data = resp.json()

        assert data["status"] == "red"
