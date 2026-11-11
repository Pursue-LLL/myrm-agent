"""A webhook trigger fires only for the caller that presents its own secret; a trigger without one never fires."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig, WebhookTrigger
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

from app.core.cron.adapters.sqlalchemy_trigger_provider import SqlAlchemyTriggerProvider


def _job(job_id: str, webhook: WebhookTrigger) -> CronJob:
    return CronJob(
        id=job_id,
        name=job_id,
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        prompt="react to the call",
        triggers=TriggerConfig(webhooks=(webhook,)),
    )


async def _handle(jobs: list[CronJob], path: str, secret: str) -> CronJob | None:
    with patch.object(SqlAlchemyTriggerProvider, "_load_triggered_jobs", new=AsyncMock(return_value=jobs)):
        return await SqlAlchemyTriggerProvider().handle_webhook(path, secret, {})


async def test_the_matching_path_and_secret_return_the_job() -> None:
    job = _job("job-1", WebhookTrigger(path="deploy", secret="s3cret"))

    assert await _handle([job], "deploy", "s3cret") is job


@pytest.mark.parametrize(("path", "secret"), [("deploy", "wrong"), ("other", "s3cret")])
async def test_a_wrong_secret_or_an_unknown_path_returns_nothing(path: str, secret: str) -> None:
    job = _job("job-1", WebhookTrigger(path="deploy", secret="s3cret"))

    assert await _handle([job], path, secret) is None


@pytest.mark.parametrize("stored", [None, ""])
async def test_a_trigger_without_a_secret_never_fires(stored: str | None) -> None:
    job = _job("job-1", WebhookTrigger(path="deploy", secret=stored))

    assert await _handle([job], "deploy", "anything") is None


async def test_a_trigger_without_a_secret_does_not_hide_the_job_that_owns_the_path() -> None:
    secretless = _job("job-1", WebhookTrigger(path="deploy", secret=None))
    owner = _job("job-2", WebhookTrigger(path="deploy", secret="s3cret"))

    assert await _handle([secretless, owner], "deploy", "s3cret") is owner
