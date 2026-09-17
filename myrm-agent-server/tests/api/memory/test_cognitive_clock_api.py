"""Tests for nested cognitive clock API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import guardian as guardian_operation


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(guardian_operation.router, prefix="/api/v1/memory")

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _fake_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_cognitive_clock_status(client: TestClient) -> None:
    fake_status = {
        "running": True,
        "last_run": 1000.0,
        "next_run": 2000.0,
        "wakeup_grace_period_active": False,
        "user_activity_detected": False,
        "seconds_since_last_user_activity": 120.0,
    }
    with patch(
        "app.lifecycle.cognitive_clock.coordinator.CognitiveClockCoordinator.get_status",
        new=AsyncMock(return_value=fake_status),
    ):
        res = client.get("/api/v1/memory/guardian/cognitive-clock/status")
        assert res.status_code == 200
        data = res.json()
        assert data["running"] is True
        assert data["wakeup_grace_period_active"] is False


def test_post_cognitive_clock_activity(client: TestClient) -> None:
    res = client.post(
        "/api/v1/memory/guardian/cognitive-clock/activity",
        json={"session_id": "sess-123", "reason": "typing"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "recorded": True, "reason": "typing"}


def test_post_cognitive_clock_trigger_t1(client: TestClient) -> None:
    with patch(
        "app.lifecycle.cognitive_clock.executors.execute_t1_session_debounce",
        new=AsyncMock(return_value=True),
    ):
        res = client.post(
            "/api/v1/memory/guardian/cognitive-clock/trigger-t1",
            json={"session_id": "sess-abc"},
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "session_id": "sess-abc"}
