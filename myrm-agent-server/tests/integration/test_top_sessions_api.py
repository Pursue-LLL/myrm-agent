"""Integration tests for Top Sessions API (A3).

Tests the complete stack: EventLog → Analytics → API → Response
Uses real session data (no mocks).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import StructuredEvent

from app.main import app


@pytest.fixture(autouse=True)
def _bypass_auth():
    if True:
        yield


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app with auth bypass."""
    return TestClient(app)


@pytest.fixture
def setup_diverse_sessions(tmp_path):
    """Setup diverse EventLog sessions for Top Sessions testing."""
    event_log_dir = tmp_path / ".event_logs"
    event_log_dir.mkdir(parents=True, exist_ok=True)

    base_time = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)

    # Session 1: Longest duration (10 hours)
    backend1 = FileEventLogBackend(event_log_dir, "session_longest")
    events1 = [
        StructuredEvent(
            session_id="session_longest",
            sequence=1,
            timestamp=base_time.timestamp(),
            event_type="session_start",
            data={},
        ),
        StructuredEvent(
            session_id="session_longest",
            sequence=2,
            timestamp=(base_time + timedelta(hours=10)).timestamp(),
            event_type="session_end",
            data={
                "summary": {
                    "total_events": 2,
                    "tool_calls": 10,
                    "duration_ms": 36000000,
                    "message_count": 20,
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                }
            },
        ),
    ]
    asyncio.run(backend1.append(events1))

    # Session 2: Most tokens (50k total)
    backend2 = FileEventLogBackend(event_log_dir, "session_most_tokens")
    events2 = [
        StructuredEvent(
            session_id="session_most_tokens",
            sequence=1,
            timestamp=(base_time + timedelta(days=1)).timestamp(),
            event_type="session_start",
            data={},
        ),
        StructuredEvent(
            session_id="session_most_tokens",
            sequence=2,
            timestamp=(base_time + timedelta(days=1, hours=2)).timestamp(),
            event_type="session_end",
            data={
                "summary": {
                    "total_events": 2,
                    "tool_calls": 5,
                    "duration_ms": 7200000,
                    "message_count": 50,
                    "input_tokens": 30000,
                    "output_tokens": 15000,
                    "cache_read_tokens": 3000,
                    "cache_write_tokens": 2000,
                }
            },
        ),
    ]
    asyncio.run(backend2.append(events2))

    # Session 3: Most messages (100 messages)
    backend3 = FileEventLogBackend(event_log_dir, "session_most_messages")
    events3 = [
        StructuredEvent(
            session_id="session_most_messages",
            sequence=1,
            timestamp=(base_time + timedelta(days=2)).timestamp(),
            event_type="session_start",
            data={},
        ),
        StructuredEvent(
            session_id="session_most_messages",
            sequence=2,
            timestamp=(base_time + timedelta(days=2, hours=3)).timestamp(),
            event_type="session_end",
            data={
                "summary": {
                    "total_events": 2,
                    "tool_calls": 20,
                    "duration_ms": 10800000,
                    "message_count": 100,
                    "input_tokens": 10000,
                    "output_tokens": 5000,
                }
            },
        ),
    ]
    asyncio.run(backend3.append(events3))

    # Session 4: Most tool calls (80 calls)
    backend4 = FileEventLogBackend(event_log_dir, "session_most_tools")
    events4 = [
        StructuredEvent(
            session_id="session_most_tools",
            sequence=1,
            timestamp=(base_time + timedelta(days=3)).timestamp(),
            event_type="session_start",
            data={},
        ),
        StructuredEvent(
            session_id="session_most_tools",
            sequence=2,
            timestamp=(base_time + timedelta(days=3, hours=4)).timestamp(),
            event_type="session_end",
            data={
                "summary": {
                    "total_events": 2,
                    "tool_calls": 80,
                    "duration_ms": 14400000,
                    "message_count": 40,
                    "input_tokens": 8000,
                    "output_tokens": 4000,
                }
            },
        ),
    ]
    asyncio.run(backend4.append(events4))

    return event_log_dir


def test_top_sessions_by_duration(test_client, setup_diverse_sessions, monkeypatch):
    """Test /api/v1/statistics/top-sessions?metric=duration."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=2",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    sessions = data["data"]

    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "session_longest"  # 36M ms = 10h
    assert sessions[0]["duration_ms"] == 36000000
    assert sessions[1]["session_id"] == "session_most_tools"  # 14.4M ms = 4h


def test_top_sessions_by_tokens(test_client, setup_diverse_sessions, monkeypatch):
    """Test /api/v1/statistics/top-sessions?metric=tokens."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=tokens&limit=1",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    sessions = data["data"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session_most_tokens"
    assert sessions[0]["total_tokens"] == 50000  # 30k+15k+3k+2k


def test_top_sessions_by_messages(test_client, setup_diverse_sessions, monkeypatch):
    """Test /api/v1/statistics/top-sessions?metric=messages."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=messages&limit=1",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    sessions = data["data"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session_most_messages"
    assert sessions[0]["message_count"] == 100


def test_top_sessions_by_tool_calls(test_client, setup_diverse_sessions, monkeypatch):
    """Test /api/v1/statistics/top-sessions?metric=tool_calls."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=tool_calls&limit=1",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    sessions = data["data"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session_most_tools"
    assert sessions[0]["tool_calls"] == 80


def test_top_sessions_invalid_metric(test_client, setup_diverse_sessions, monkeypatch):
    """Test API with invalid metric returns error."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=invalid",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 400  # validation_error


def test_top_sessions_empty_data(test_client, tmp_path, monkeypatch):
    """Test API with no EventLog data."""
    empty_log_dir = tmp_path / "empty_logs"
    empty_log_dir.mkdir()

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(empty_log_dir),
    )

    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration",
        headers={"Authorization": "Bearer local"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["data"] == []


def test_top_sessions_boundary_params(test_client, setup_diverse_sessions, monkeypatch):
    """Test boundary values for limit parameter."""
    event_log_dir = setup_diverse_sessions

    monkeypatch.setattr(
        "app.config.settings.settings.database.event_log_dir",
        str(event_log_dir),
    )

    # Min limit: 1
    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=1",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200

    # Max limit: 50
    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=50",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200

    # Invalid: 0
    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=0",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422

    # Invalid: negative
    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=-1",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422

    # Invalid: over 50
    response = test_client.get(
        "/api/v1/statistics/top-sessions?metric=duration&limit=100",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422
