"""Tests for read-it-later cron hygiene migration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

from app.core.cron.adapters.wiki_source_sync_runner import WIKI_SOURCE_SYNC_COMMAND
from app.services.wiki.source_sync.read_it_later_hygiene import (
    is_stale_read_it_later_job,
    migrate_stale_read_it_later_jobs,
)


def _legacy_job(*, job_id: str = "job-1") -> CronJob:
    return CronJob(
        id=job_id,
        user_id="default",
        name="Second Brain · Read-it-Later",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"),
        prompt="Run the read-it-later ingestion pipeline",
        tools_allowed=("file_ops",),
    )


def _router_job(*, job_id: str = "job-2") -> CronJob:
    return CronJob(
        id=job_id,
        user_id="default",
        name="Second Brain · Read-it-Later",
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"),
        prompt="Wiki source sync job (router mode).",
        command=WIKI_SOURCE_SYNC_COMMAND,
    )


def test_is_stale_detects_legacy_agent_job() -> None:
    assert is_stale_read_it_later_job(_legacy_job()) is True


def test_is_stale_skips_router_job() -> None:
    assert is_stale_read_it_later_job(_router_job()) is False


@pytest.mark.asyncio
async def test_migrate_recreates_stale_job() -> None:
    legacy = _legacy_job()
    recreated = _router_job(job_id="job-new")
    mgr = MagicMock()
    mgr.list_jobs = AsyncMock(return_value=[legacy])
    mgr.delete_job = AsyncMock()
    mgr.create_job = AsyncMock(return_value=recreated)

    fill = MagicMock(
        job_type="router",
        prompt="Wiki source sync job (router mode).",
        required_capabilities=(),
        tools_allowed=(),
        session_target="isolated",
        deduplicate=True,
        skip_if_active=True,
        timeout_seconds=120,
        pre_condition_script=None,
        command=WIKI_SOURCE_SYNC_COMMAND,
    )

    with (
        patch("app.services.wiki.source_sync.read_it_later_hygiene.get_cron_manager", return_value=mgr),
        patch("app.services.wiki.source_sync.read_it_later_hygiene.fill_blueprint", return_value=fill),
    ):
        result = await migrate_stale_read_it_later_jobs()

    assert result.migrated_count == 1
    assert result.id_remaps == {"job-1": "job-new"}
    mgr.delete_job.assert_awaited_once_with("job-1", "default")
    mgr.create_job.assert_awaited_once()
