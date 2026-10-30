"""A probe script that crashes is a failed run the user hears about; a probe that says skip stays a skip.

The Financial Monitor blueprint ships a zero-LLM probe that raises when every price source fails, and a failure alert
for exactly that. The real blueprint script runs here in the real sandboxed condition, with the network cut, inside the
real scheduler, executor and manager over the in-memory store; only the runner and the delivery are stand-ins.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.python_condition import SandboxedPythonCondition
from app.core.cron.blueprint_job_spec import fill_job_spec

USER = "user-1"
EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
MONITOR_VALUES = {
    "time": "08:00",
    "weekdays": "weekdays",
    "asset": "bitcoin",
    "quote_currency": "usd",
    "lower_bound": "50000",
    "upper_bound": "70000",
    "source": "coingecko",
}
NETWORK_DOWN = (
    "import urllib.request\ndef _down(*args, **kwargs):\n    raise OSError('network down')\nurllib.request.urlopen = _down\n"
)


class _Delivery:
    def __init__(self) -> None:
        self.results: list[JobResult] = []

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        self.results.append(result)

    @property
    def alerts(self) -> list[str]:
        return [r.output for r in self.results if r.success and r.output.startswith("Cron job")]


class _Runner:
    def __init__(self) -> None:
        self.runs = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        return JobResult(success=True, output="done")


@dataclass
class Stack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler
    runner: _Runner
    delivery: _Delivery

    async def create_monitor(self, probe: str | None = None, schedule: Schedule = EVERY_HOUR) -> CronJob:
        """The Financial Monitor blueprint's job; ``probe`` replaces its script, and the network is down for its own."""
        spec = fill_job_spec("financial_monitor_simple", MONITOR_VALUES, locale="en", tz=None)
        assert spec is not None and spec.pre_condition_script is not None
        return await self.manager.create_job(
            USER,
            spec.name,
            spec.job_type,
            schedule,
            prompt=spec.prompt,
            deduplicate=spec.deduplicate,
            skip_if_active=spec.skip_if_active,
            timeout_seconds=spec.timeout_seconds or 300,
            failure_alert=spec.failure_alert,
            pre_condition_script=probe or NETWORK_DOWN + spec.pre_condition_script,
        )

    async def dispatch(self, job: CronJob) -> None:
        snapshot = await self.store.get_job(job.id)
        await self.store.claim_due([job.id])
        await self.scheduler._execute_and_persist(snapshot)
        await asyncio.sleep(0)  # the failure alert is sent from a task the executor starts

    async def stored(self, job: CronJob) -> CronJob:
        found = await self.store.get_job(job.id)
        assert found is not None
        return found


@pytest.fixture
def stack() -> Stack:
    store = InMemoryCronStore()
    runner, delivery = _Runner(), _Delivery()
    scheduler = CronScheduler(
        store,
        {JobType.ROUTER: runner},
        delivery,
        config=CronConfig(max_per_user=1),
        pre_condition=SandboxedPythonCondition(timeout_seconds=30),
    )
    return Stack(store, CronManager(store, scheduler), scheduler, runner, delivery)


async def test_the_monitor_whose_sources_all_fail_is_a_failed_run_with_an_alert(stack: Stack) -> None:
    job = await stack.create_monitor()

    await stack.dispatch(job)

    stored = await stack.stored(job)
    (run,) = await stack.store.list_runs(job.id)
    assert run.status == RunStatus.ERROR
    assert run.error is not None and run.error.startswith(
        "Pre-flight probe failed: exit code 1: RuntimeError: all_sources_failed"
    )
    assert stack.runner.runs == 0
    assert stored.status == JobStatus.ACTIVE and stored.consecutive_failures == 1
    assert stored.next_run_at is not None and stored.last_run_at is not None
    assert stored.next_run_at - stored.last_run_at > timedelta(minutes=30)
    (alert,) = stack.delivery.alerts
    assert "failed 1 consecutive times" in alert and "all_sources_failed" in alert


async def test_a_one_shot_job_whose_probe_crashes_is_paused_not_consumed(stack: Stack) -> None:
    schedule = Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1))
    job = await stack.create_monitor("raise RuntimeError('boom')", schedule)
    assert job.delete_after_run

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.status == JobStatus.PAUSED
    assert stored.last_error == "Pre-flight probe failed: exit code 1: RuntimeError: boom"


async def test_a_probe_that_prints_skip_is_still_a_skip(stack: Stack) -> None:
    job = await stack.create_monitor("print('[SKIP]')")

    await stack.dispatch(job)

    stored = await stack.stored(job)
    assert stored.last_status == RunStatus.SKIPPED and stored.consecutive_failures == 0
    assert stack.runner.runs == 0 and stack.delivery.results == []
