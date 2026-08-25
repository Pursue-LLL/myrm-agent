"""Unit tests for ConnectorHealthService and Connector Health API."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.api import (
    ConnectorErrorCategory,
    ConnectorHealthStatus,
)

from app.database.models.cron import CronJobModel, CronRunModel
from app.services.cron.connector_health_service import ConnectorHealthService


@pytest.mark.asyncio
async def test_connector_health_service_aggregation() -> None:
    job = CronJobModel(
        id="job_sync_1",
        name="Sync Data",
        job_type="agent",
        status="active",
        schedule={"kind": "interval", "interval_ms": 60000},
        delivery={"channel": "webhook", "target": "https://api.example.com/hook?token=secret123"},
        consecutive_failures=3,
        last_error="Webhook returned 502: Bad Gateway",
    )

    run1 = CronRunModel(
        id="run_1",
        job_id="job_sync_1",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=100,
        status="ok",
        delivery_status="failed",
        delivery_error="Webhook returned 502: Bad Gateway",
    )

    with patch("app.services.cron.connector_health_service.UnitOfWork") as mock_uow_cls:
        mock_uow = AsyncMock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=None)
        mock_uow_cls.return_value = mock_uow

        mock_job_res = AsyncMock()
        mock_scalars_job = AsyncMock()
        mock_scalars_job.all = AsyncMock(return_value=[job])
        mock_job_res.scalars = AsyncMock(return_value=mock_scalars_job)

        # In SQLAlchemy AsyncSession.execute, scalars() is sync and returns a ScalarResult
        from unittest.mock import MagicMock
        sync_job_res = MagicMock()
        sync_job_res.scalars.return_value.all.return_value = [job]

        sync_run_res = MagicMock()
        sync_run_res.scalars.return_value.all.return_value = [run1]

        mock_session.execute = AsyncMock(side_effect=[sync_job_res, sync_run_res])

        summaries = await ConnectorHealthService.get_all_connectors_health(window_hours=24)

        assert len(summaries) == 1
        s = summaries[0]
        assert s.channel == "webhook"
        assert "secret123" not in s.target
        assert s.status == ConnectorHealthStatus.DEGRADED or s.status == ConnectorHealthStatus.DOWN
        assert s.last_error_category == ConnectorErrorCategory.HTTP_SERVER_ERROR
        assert s.fix_suggestion is not None
        assert "job_sync_1" in s.bound_job_ids
