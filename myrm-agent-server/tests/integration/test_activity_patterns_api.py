"""Integration tests for Activity Patterns API (A2).

Tests the complete stack: EventLog → Analytics → API → Response
Uses real agent sessions and event logs (no mocks).

Skipped: module-level asyncio.Queue singletons in app startup bind to the
import-time event loop, which conflicts with TestClient's event loop.
Tracked as a known issue for app-level TestClient integration tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import StructuredEvent

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="statistics")
pytestmark = pytest.mark.skip(
    reason="event-loop binding conflict: module-level Queue singletons "
    "bind to import-time loop, conflicting with TestClient's loop"
)


@pytest.fixture
def test_client():
    """Create a test client with noop lifespan and auth bypass.

    Uses noop lifespan to avoid event-loop binding conflicts with module-level
    Queue singletons (e.g. MaintenanceDaemon, ABTestManager) initialized during
    app startup. Monkeypatches resolve_identity to bypass auth.
    """
    from contextlib import asynccontextmanager

    from app.core.security.auth.identity import ResolvedIdentity

    @asynccontextmanager
    async def _noop_lifespan(_a):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan

    import app.core.security.auth.identity as auth_mod

    original_resolve = auth_mod.resolve_identity

    def _always_local(**_kwargs):
        return ResolvedIdentity(
            user_id="local-user",
            auth_source="loopback",
            client_ip="127.0.0.1",
            loopback=True,
            private_net=True,
        )

    auth_mod.resolve_identity = _always_local

    try:
        yield TestClient(app)
    finally:
        app.router.lifespan_context = original_lifespan
        auth_mod.resolve_identity = original_resolve


@pytest.fixture
def setup_event_logs(tmp_path):
    """Setup EventLog data for testing."""
    event_log_dir = tmp_path / ".event_logs"
    event_log_dir.mkdir(parents=True, exist_ok=True)

    base_time = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    # Create 3 sessions across 3 days
    for session_idx in range(3):
        session_id = f"test_session_{session_idx}"
        backend = FileEventLogBackend(event_log_dir, session_id)

        events = [
            StructuredEvent(
                session_id=session_id,
                sequence=1,
                timestamp=(base_time + timedelta(days=session_idx)).timestamp(),
                event_type="session_start",
                data={},
            ),
            StructuredEvent(
                session_id=session_id,
                sequence=2,
                timestamp=(base_time + timedelta(days=session_idx, hours=2)).timestamp(),
                event_type="session_end",
                data={
                    "summary": {
                        "total_events": 2,
                        "tool_calls": session_idx + 1,
                        "errors": 0,
                        "approvals": 0,
                        "compactions": 0,
                        "failovers": 0,
                        "security_decisions": 0,
                        "duration_ms": 7200000,
                    }
                },
            ),
        ]

        asyncio.run(backend.append(events))

    return event_log_dir


def test_activity_api_basic(test_client, setup_event_logs, tmp_path, monkeypatch):
    """Test /api/v1/statistics/activity endpoint returns correct data."""
    event_log_dir = setup_event_logs

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    # Make request
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=30",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "data" in data

    patterns = data["data"]
    assert patterns["active_days"] == 3
    assert patterns["max_streak"] == 3
    assert len(patterns["daily_activities"]) == 3
    assert "by_day_of_week" in patterns
    assert "by_hour" in patterns
    assert "busiest_day_of_week" in patterns
    assert "busiest_hour" in patterns


def test_activity_api_empty_data(test_client, tmp_path, monkeypatch):
    """Test API with no EventLog data."""
    empty_log_dir = tmp_path / "empty_logs"
    empty_log_dir.mkdir()

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(empty_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=30",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    patterns = data["data"]
    assert patterns["active_days"] == 0
    assert patterns["max_streak"] == 0
    assert len(patterns["daily_activities"]) == 0


def test_activity_api_no_directory(test_client, tmp_path, monkeypatch):
    """Test API when EventLog directory does not exist."""
    non_existent_dir = tmp_path / "non_existent"

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(non_existent_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=30",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    # Should return empty structure
    assert data["success"] is True
    patterns = data["data"]
    assert patterns["active_days"] == 0


def test_activity_api_boundary_params(test_client, setup_event_logs, monkeypatch):
    """Test boundary values for time_range_days parameter."""
    event_log_dir = setup_event_logs

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    # Min value: 1 day
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=1",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200

    # Max value: 365 days
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=365",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200

    # Invalid: 0 (should fail validation)
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=0",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422  # Validation error

    # Invalid: negative
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=-1",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422

    # Invalid: over 365
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=999",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422


def test_activity_api_local_mode_auto_auth(test_client, setup_event_logs, monkeypatch):
    """Test API in Local mode auto-injects user (no auth header needed)."""
    event_log_dir = setup_event_logs

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    # No Authorization header
    response = test_client.get("/api/v1/statistics/activity?time_range_days=30")

    # Local mode auto-authenticates
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_activity_api_response_time(test_client, setup_event_logs, monkeypatch):
    """Test API response time < 1s."""
    import time

    event_log_dir = setup_event_logs

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    start_time = time.perf_counter()
    response = test_client.get(
        "/api/v1/statistics/activity?time_range_days=30",
        headers={"Authorization": "Bearer local"},
    )
    elapsed = time.perf_counter() - start_time

    assert response.status_code == 200
    assert elapsed < 1.0, f"API response took {elapsed:.2f}s (should be < 1s)"


def test_activity_api_concurrent_requests(test_client, setup_event_logs, monkeypatch):
    """Test 10+ concurrent requests don't cause errors."""
    from concurrent.futures import ThreadPoolExecutor

    event_log_dir = setup_event_logs

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    def make_request():
        response = test_client.get(
            "/api/v1/statistics/activity?time_range_days=30",
            headers={"Authorization": "Bearer local"},
        )
        return response.status_code

    # Run 20 concurrent requests
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: make_request(), range(20)))

    # All should succeed
    assert all(status == 200 for status in results)
