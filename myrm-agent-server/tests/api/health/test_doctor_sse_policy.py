"""Doctor endpoint SSE policy integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.health_alert_policy import reset_health_alert_dedup_for_tests
from app.core.infra.health.health_snapshot import HealthSnapshot
from app.services.event.app_event_bus import AppEventType
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_minimal_app(preset="health"))


def _warn_system_resources_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        harness_reports=(
            HealthReport(
                component_name="SystemResources",
                status="warn",
                message="CPU usage is high.",
                detail="CPU: 91.0%, Memory: 70.0% (8.0/16.0GB)",
            ),
            HealthReport(
                component_name="Network",
                status="pass",
                message="Network is healthy.",
            ),
        ),
        server_reports=(),
    )


def _database_fail_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        harness_reports=(
            HealthReport(
                component_name="Database",
                status="fail",
                message="Database connection failed.",
                detail="sqlite unavailable",
            ),
        ),
        server_reports=(),
    )


def _capture_health_alerts() -> tuple[MagicMock, list[object]]:
    published: list[object] = []
    mock_bus = MagicMock()

    def _publish(event: object) -> None:
        published.append(event)

    mock_bus.publish.side_effect = _publish
    return mock_bus, published


def test_doctor_system_resources_warn_does_not_publish_health_alert(client: TestClient) -> None:
    """Regression: SystemResources warn must not fan out as chat SSE toast."""
    mock_bus, published = _capture_health_alerts()
    reset_health_alert_dedup_for_tests()

    with (
        patch(
            "app.core.infra.health.health_snapshot.collect_health_snapshot",
            return_value=_warn_system_resources_snapshot(),
        ),
        patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus),
    ):
        response = client.get("/api/v1/health/doctor")

    assert response.status_code == 200
    health_alerts = [
        event
        for event in published
        if getattr(event, "event_type", None) == AppEventType.HEALTH_ALERT
    ]
    assert health_alerts == []

    harness = response.json()["harness"]
    sr = next(r for r in harness if r["component_name"] == "SystemResources")
    assert sr["status"] == "warn"
    assert sr["message"] == "CPU usage is high."


def test_doctor_database_fail_publishes_health_alert(client: TestClient) -> None:
    """Product-critical fail still reaches SSE subscribers."""
    mock_bus, published = _capture_health_alerts()
    reset_health_alert_dedup_for_tests()

    with (
        patch(
            "app.core.infra.health.health_snapshot.collect_health_snapshot",
            return_value=_database_fail_snapshot(),
        ),
        patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus),
    ):
        response = client.get("/api/v1/health/doctor")

    assert response.status_code == 200
    health_alerts = [
        event
        for event in published
        if getattr(event, "event_type", None) == AppEventType.HEALTH_ALERT
    ]
    assert len(health_alerts) == 1
    assert health_alerts[0].data["component"] == "Database"
    assert health_alerts[0].data["status"] == "fail"


def test_doctor_database_fail_deduped_within_window(client: TestClient) -> None:
    """Repeated doctor refresh should not spam identical fail alerts."""
    mock_bus, published = _capture_health_alerts()
    reset_health_alert_dedup_for_tests()

    with (
        patch(
            "app.core.infra.health.health_snapshot.collect_health_snapshot",
            return_value=_database_fail_snapshot(),
        ),
        patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus),
    ):
        first = client.get("/api/v1/health/doctor")
        second = client.get("/api/v1/health/doctor")

    assert first.status_code == 200
    assert second.status_code == 200
    health_alerts = [
        event
        for event in published
        if getattr(event, "event_type", None) == AppEventType.HEALTH_ALERT
    ]
    assert len(health_alerts) == 1
