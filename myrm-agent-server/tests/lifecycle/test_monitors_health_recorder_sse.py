"""Regression tests: health history recorder must not fan out HEALTH_ALERT SSE."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.health_snapshot import HealthSnapshot
from app.services.event.app_event_bus import AppEventType


def _sample_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        harness_reports=(
            HealthReport(
                component_name="SystemResources",
                status="warn",
                message="CPU usage is high.",
            ),
            HealthReport(
                component_name="Network",
                status="pass",
                message="Network is healthy.",
            ),
        ),
        server_reports=(),
    )


@asynccontextmanager
async def _mock_session():
    class _Session:
        async def execute(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    yield _Session()


class TestHealthHistoryRecorderSsePolicy:
    def test_recorder_job_source_never_references_health_alert(self) -> None:
        """Static guard: job body must not publish HEALTH_ALERT or call doctor alerts."""
        from app.lifecycle import monitors

        source = inspect.getsource(monitors._health_history_recorder_job)
        assert "HEALTH_ALERT" not in source
        assert "publish_health_alerts" not in source
        assert "system_doctor" not in source

    @pytest.mark.asyncio
    async def test_recorder_job_publishes_status_updated_not_health_alert(self) -> None:
        """Runtime guard: mocked recorder run only emits HEALTH_STATUS_UPDATED."""
        published: list[object] = []
        mock_bus = MagicMock()

        def _publish(event: object) -> None:
            published.append(event)

        mock_bus.publish.side_effect = _publish

        with (
            patch(
                "app.core.infra.health.health_snapshot.collect_health_snapshot",
                return_value=_sample_snapshot(),
            ),
            patch("app.database.connection.get_session", _mock_session),
            patch("app.services.event.app_event_bus.get_event_bus", return_value=mock_bus),
        ):
            from app.lifecycle.monitors import _health_history_recorder_job

            await _health_history_recorder_job()

        health_alerts = [
            event
            for event in published
            if getattr(event, "event_type", None) == AppEventType.HEALTH_ALERT
        ]
        status_updates = [
            event
            for event in published
            if getattr(event, "event_type", None) == AppEventType.HEALTH_STATUS_UPDATED
        ]
        assert health_alerts == []
        assert len(status_updates) == 1
