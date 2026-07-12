"""Unit tests for health alert publish policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.health_alert_policy import (
    publish_health_alerts,
    reset_health_alert_dedup_for_tests,
    should_publish_health_alert,
)


@pytest.fixture(autouse=True)
def _clear_dedup() -> None:
    reset_health_alert_dedup_for_tests()


class TestShouldPublishHealthAlert:
    def test_system_resources_never_pushes(self) -> None:
        assert should_publish_health_alert("SystemResources", "warn") is False
        assert should_publish_health_alert("SystemResources", "fail") is False

    def test_warn_never_pushes(self) -> None:
        assert should_publish_health_alert("Database", "warn") is False

    def test_fail_pushes_for_critical_components(self) -> None:
        assert should_publish_health_alert("Database", "fail") is True
        assert should_publish_health_alert("AgentEngine", "fail") is True

    def test_nonlisted_fail_does_not_push(self) -> None:
        assert should_publish_health_alert("Tokenizer", "fail") is False
        assert should_publish_health_alert("HookSystem", "fail") is False


class TestPublishHealthAlerts:
    def test_system_resources_warn_not_published(self) -> None:
        mock_bus = MagicMock()
        reports = (
            HealthReport(
                component_name="SystemResources",
                status="warn",
                message="CPU high",
            ),
        )
        with patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus):
            publish_health_alerts(reports, layer="harness")
        mock_bus.publish.assert_not_called()

    def test_database_fail_published_once_within_dedup_window(self) -> None:
        mock_bus = MagicMock()
        reports = (
            HealthReport(
                component_name="Database",
                status="fail",
                message="DB down",
            ),
        )
        with patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus):
            publish_health_alerts(reports, layer="harness")
            publish_health_alerts(reports, layer="harness")
        assert mock_bus.publish.call_count == 1

    def test_database_fail_published_with_layer(self) -> None:
        mock_bus = MagicMock()
        reports = (
            HealthReport(
                component_name="Database",
                status="fail",
                message="DB down",
            ),
        )
        with patch("app.core.infra.health.health_alert_policy.get_event_bus", return_value=mock_bus):
            publish_health_alerts(reports, layer="server")
        event = mock_bus.publish.call_args[0][0]
        assert event.data["layer"] == "server"
        assert event.data["component"] == "Database"
