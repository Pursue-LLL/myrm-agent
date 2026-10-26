"""Cron lifecycle of the per-agent sync job, against the real cron manager over the in-memory store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind, SessionTarget

from app.core.cron.adapters.wiki_router_job_runner import WIKI_IMA_SYNC_COMMAND
from app.services.wiki.source_sync.ima import job as job_module

_HOURLY = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3600 * 1000)
_NAMES = {
    "zh": "ima 知识库同步",
    "zh-TW": "ima 知识库同步",
    "en": "ima Knowledge Sync",
    "de": "ima Knowledge Sync",
    "ja": "ima Knowledge Sync",
    "ko": "ima Knowledge Sync",
}
# The description is shown under the job name in the cron list; it must not expose how the job is run.
_IMPLEMENTATION_TERMS = ("router", "prompt", "cron", "路由", "提示词")


class _NoDelivery:
    async def deliver(self, job: CronJob, result: object) -> None:
        return None


@dataclass
class Cron:
    manager: CronManager
    store: InMemoryCronStore

    async def jobs(self) -> list[CronJob]:
        return await self.manager.list_jobs(job_module._USER_ID)

    async def only(self) -> CronJob:
        (job,) = await self.jobs()
        return job

    async def create_other(self, command: str) -> CronJob:
        return await self.manager.create_job(
            job_module._USER_ID, command, JobType.ROUTER, _HOURLY, prompt="other job", command=command
        )

    async def defer_next_run(self) -> None:
        job = await self.only()
        job.next_run_at = datetime.now(UTC) + timedelta(days=1)
        await self.store.save_job(job)


def _is_due(job: CronJob) -> bool:
    return job.next_run_at is not None and job.next_run_at <= datetime.now(UTC)


@pytest.fixture
def cron(monkeypatch: pytest.MonkeyPatch) -> Cron:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    fake = Cron(manager=CronManager(store, scheduler), store=store)
    monkeypatch.setattr(job_module, "get_cron_manager", lambda: fake.manager)
    return fake


async def test_start_creates_one_interval_router_job_and_runs_it_now(cron: Cron) -> None:
    await job_module.start_job(None, locale="en")

    job = await cron.only()
    assert job.command == WIKI_IMA_SYNC_COMMAND == "__wiki_ima_sync__"
    assert job.job_type == JobType.ROUTER and job.session_target == SessionTarget.ISOLATED
    assert job.schedule.kind == ScheduleKind.INTERVAL and job.schedule.interval_ms == 6 * 3600 * 1000
    assert job.timeout_seconds == 600 and job.agent_id is None
    assert job.name == "ima Knowledge Sync" and job.status == JobStatus.ACTIVE
    assert _is_due(job)


@pytest.mark.parametrize("locale", list(_NAMES))
async def test_job_copy_follows_the_locale_and_never_exposes_how_the_job_runs(cron: Cron, locale: str) -> None:
    await job_module.start_job(None, locale=locale)

    job = await cron.only()
    assert job.name == _NAMES[locale]
    description = (job.prompt or "").strip()
    assert "ima" in description
    assert not any(term in description.lower() for term in _IMPLEMENTATION_TERMS)


async def test_the_job_description_is_localised_like_its_name(cron: Cron) -> None:
    await job_module.start_job(None, locale="zh-CN")
    await job_module.start_job("agent-en", locale="en-US")

    zh, en = await job_module.find_job(None), await job_module.find_job("agent-en")
    assert zh is not None and en is not None
    assert zh.prompt != en.prompt
    assert zh.name == "ima 知识库同步" and en.name.startswith("ima Knowledge Sync")


async def test_starting_twice_reuses_the_job_and_resumes_a_paused_one(cron: Cron) -> None:
    await job_module.start_job(None, locale="en")
    await job_module.pause_job(None)
    paused = await cron.only()
    assert paused.status == JobStatus.PAUSED
    await cron.defer_next_run()

    await job_module.start_job(None, locale="en")

    job = await cron.only()
    assert job.id == paused.id and job.status == JobStatus.ACTIVE and _is_due(job)


async def test_jobs_are_scoped_per_agent_and_other_commands_are_ignored(cron: Cron) -> None:
    await cron.create_other("__wiki_source_sync__")
    await job_module.start_job("agent-a", locale="en")

    found = await job_module.find_job("agent-a")
    assert found is not None and found.command == WIKI_IMA_SYNC_COMMAND and found.agent_id == "agent-a"
    assert await job_module.find_job(None) is None
    assert await job_module.find_job("agent-b") is None


async def test_pause_and_resume_report_whether_a_job_exists(cron: Cron) -> None:
    assert await job_module.pause_job(None) is False
    assert await job_module.resume_job(None) is False

    await job_module.start_job(None, locale="en")
    assert await job_module.pause_job(None) is True
    assert (await cron.only()).status == JobStatus.PAUSED
    await cron.defer_next_run()

    assert await job_module.resume_job(None) is True
    resumed = await cron.only()
    assert resumed.status == JobStatus.ACTIVE and _is_due(resumed)


async def test_stop_all_removes_only_ima_jobs(cron: Cron) -> None:
    keep = await cron.create_other("__wiki_dedup__")
    await job_module.start_job(None, locale="en")
    await job_module.start_job("agent-a", locale="en")

    assert await job_module.stop_all_jobs() == 2
    assert [job.id for job in await cron.jobs()] == [keep.id]


async def test_trigger_if_active_skips_paused_and_missing_jobs(cron: Cron) -> None:
    await job_module.trigger_if_active(None)
    assert await cron.jobs() == []

    await job_module.start_job(None, locale="en")
    await job_module.pause_job(None)
    await cron.defer_next_run()
    await job_module.trigger_if_active(None)
    assert not _is_due(await cron.only())

    await job_module.resume_job(None)
    await cron.defer_next_run()
    await job_module.trigger_if_active(None)
    assert _is_due(await cron.only())


async def test_is_job_active_follows_the_job_through_pause_resume_and_removal(cron: Cron) -> None:
    assert not await job_module.is_job_active(None)

    await job_module.start_job(None, locale="en")
    assert await job_module.is_job_active(None)

    await job_module.pause_job(None)
    assert not await job_module.is_job_active(None)

    await job_module.resume_job(None)
    assert await job_module.is_job_active(None)

    await job_module.stop_all_jobs()
    assert not await job_module.is_job_active(None)


async def test_is_job_active_is_asked_per_agent(cron: Cron) -> None:
    await job_module.start_job("agent-a", locale="en")

    assert await job_module.is_job_active("agent-a")
    assert not await job_module.is_job_active("agent-b")
    assert not await job_module.is_job_active(None)
