"""Contract tests for Behavioral Insights endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.api import RoutineMeasurement

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager


@pytest.fixture
def behavioral_client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    async def _mock_db() -> AsyncMock:
        return AsyncMock()

    def _mock_manager() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_crud_memory_manager] = _mock_manager
    return TestClient(app)


def test_get_behavioral_insights_endpoint(behavioral_client: TestClient) -> None:
    mock_routine = RoutineMeasurement(
        hour_histogram=[0] * 24,
        workday_hour_histogram=[0] * 24,
        weekend_hour_histogram=[0] * 24,
        weekday_histogram=[0] * 7,
        reply_latency_p50_ms=45000.0,
        reply_latency_p90_ms=90000.0,
        self_message_count=35,
        latency_sample_count=18,
        channel_distribution={"slack": 35},
        peak_active_window="10:00 - 14:00",
        workday_peak_window="10:00 - 14:00",
        weekend_peak_window=None,
        top_collaborators=[("Charlie", 12), ("Dana", 8)],
    )

    with patch(
        "app.api.memory.operations.command_center.BehavioralMeasurementService.measure",
        new=AsyncMock(return_value=mock_routine),
    ):
        resp = behavioral_client.get("/api/memory/command-center/behavioral-insights?lookback_days=14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply_latency_p50_ms"] == 45000.0
        assert data["self_message_count"] == 35
        assert data["workday_peak_window"] == "10:00 - 14:00"
        assert len(data["top_collaborators"]) == 2
        assert data["top_collaborators"][0] == ["Charlie", 12]
        assert data["source"] == "computed_deterministic"


def test_get_behavioral_insights_with_client_timezone(behavioral_client: TestClient) -> None:
    mock_routine = RoutineMeasurement(
        hour_histogram=[0] * 24,
        workday_hour_histogram=[0] * 24,
        weekend_hour_histogram=[0] * 24,
        weekday_histogram=[0] * 7,
        self_message_count=10,
        latency_sample_count=5,
    )

    with patch(
        "app.api.memory.operations.command_center.BehavioralMeasurementService.measure",
        new=AsyncMock(return_value=mock_routine),
    ):
        resp = behavioral_client.get(
            "/api/memory/command-center/behavioral-insights?client_timezone=Asia/Shanghai&locale_anchor=zh"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected_timezone"] == "Asia/Shanghai"
        assert data["locale_anchor"] == "zh"
        assert data["offset_minutes"] == 480


def test_trigger_behavioral_sync_endpoint(behavioral_client: TestClient) -> None:
    with patch(
        "app.api.memory.operations.command_center.BehavioralMeasurementService.sync_profile_attributes",
        new=AsyncMock(return_value=["routine_active_hours", "routine_top_collaborators"]),
    ):
        resp = behavioral_client.post("/api/memory/command-center/behavioral-sync?lookback_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 2
        assert "routine_active_hours" in data["updated_profile_keys"]
