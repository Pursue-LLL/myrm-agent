"""Cron lifecycle of the per-agent sync job, against an in-memory cron manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType, ScheduleKind, SessionTarget

from app.core.cron.adapters.wiki_router_job_runner import WIKI_IMA_SYNC_COMMAND
from app.services.wiki.source_sync.ima import job as job_module


@dataclass
class FakeCron:
    jobs: list[SimpleNamespace] = field(default_factory=list)
    created: list[dict[str, object]] = field(default_factory=list)
    triggered: list[str] = field(default_factory=list)

    async def list_jobs(self, user_id: str) -> list[SimpleNamespace]:
        return list(self.jobs)

    async def create_job(self, user_id: str, name: str, job_type: JobType, schedule: object, **kwargs: object) -> SimpleNamespace:
        self.created.append({"name": name, "job_type": job_type, "schedule": schedule, **kwargs})
        job = SimpleNamespace(
            id=f"job{len(self.jobs) + 1}",
            command=kwargs["command"],
            agent_id=kwargs["agent_id"],
            status=JobStatus.ACTIVE,
            next_run_at=None,
        )
        self.jobs.append(job)
        return job

    def _get(self, job_id: str) -> SimpleNamespace:
        return next(job for job in self.jobs if job.id == job_id)

    async def pause_job(self, job_id: str, user_id: str) -> None:
        self._get(job_id).status = JobStatus.PAUSED

    async def resume_job(self, job_id: str, user_id: str) -> None:
        self._get(job_id).status = JobStatus.ACTIVE

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        self.jobs.remove(self._get(job_id))
        return True

    async def trigger_now(self, job_id: str, user_id: str) -> bool:
        self.triggered.append(job_id)
        return self._get(job_id).status == JobStatus.ACTIVE


@pytest.fixture
def cron(monkeypatch: pytest.MonkeyPatch) -> FakeCron:
    fake = FakeCron()
    monkeypatch.setattr(job_module, "get_cron_manager", lambda: fake)
    return fake


async def test_start_creates_one_interval_router_job_and_runs_it_now(cron: FakeCron) -> None:
    await job_module.start_job(None, locale="en")

    created = cron.created[0]
    assert created["command"] == WIKI_IMA_SYNC_COMMAND == "__wiki_ima_sync__"
    assert created["job_type"] == JobType.ROUTER and created["session_target"] == SessionTarget.ISOLATED
    assert created["schedule"].kind == ScheduleKind.INTERVAL and created["schedule"].interval_ms == 6 * 3600 * 1000
    assert created["timeout_seconds"] == 600 and created["agent_id"] is None
    assert created["name"] == "ima Knowledge Sync"
    assert cron.triggered == ["job1"]


async def test_job_name_follows_the_locale(cron: FakeCron) -> None:
    await job_module.start_job("agent-1", locale="zh-TW")
    assert cron.created[0]["name"] == "ima 知识库同步"


async def test_starting_twice_reuses_the_job_and_resumes_a_paused_one(cron: FakeCron) -> None:
    await job_module.start_job(None, locale="en")
    await job_module.pause_job(None)
    await job_module.start_job(None, locale="en")

    assert len(cron.jobs) == 1 and cron.jobs[0].status == JobStatus.ACTIVE
    assert cron.triggered == ["job1", "job1"]


async def test_jobs_are_scoped_per_agent_and_other_commands_are_ignored(cron: FakeCron) -> None:
    cron.jobs.append(SimpleNamespace(id="other", command="__wiki_source_sync__", agent_id=None, status=JobStatus.ACTIVE))
    await job_module.start_job("agent-a", locale="en")

    assert (await job_module.find_job("agent-a")).id == "job2"
    assert await job_module.find_job(None) is None
    assert await job_module.find_job("agent-b") is None


async def test_pause_and_resume_report_whether_a_job_exists(cron: FakeCron) -> None:
    assert await job_module.pause_job(None) is False
    assert await job_module.resume_job(None) is False

    await job_module.start_job(None, locale="en")
    assert await job_module.pause_job(None) is True
    assert cron.jobs[0].status == JobStatus.PAUSED
    cron.triggered.clear()
    assert await job_module.resume_job(None) is True
    assert cron.jobs[0].status == JobStatus.ACTIVE and cron.triggered == ["job1"]


async def test_stop_all_removes_only_ima_jobs(cron: FakeCron) -> None:
    cron.jobs.append(SimpleNamespace(id="keep", command="__wiki_dedup__", agent_id=None, status=JobStatus.ACTIVE))
    await job_module.start_job(None, locale="en")
    await job_module.start_job("agent-a", locale="en")

    assert await job_module.stop_all_jobs() == 2
    assert [job.id for job in cron.jobs] == ["keep"]


async def test_trigger_if_active_skips_paused_and_missing_jobs(cron: FakeCron) -> None:
    await job_module.trigger_if_active(None)
    await job_module.start_job(None, locale="en")
    await job_module.pause_job(None)
    cron.triggered.clear()

    await job_module.trigger_if_active(None)
    assert cron.triggered == []
