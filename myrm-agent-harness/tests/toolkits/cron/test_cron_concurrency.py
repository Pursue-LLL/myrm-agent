"""The scheduler runs at most ``CronConfig.max_concurrent`` jobs at once; a job over the cap waits for a slot.

The default cap is three: it is what keeps a burst of due jobs from starving the agent runtime of model and tool
capacity. Every test drives the real scheduler, executor and manager over the in-memory store; only the runner and
the delivery are stand-ins.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, JobType, Schedule, ScheduleKind

EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
DEFAULT_CAP = 3


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


@dataclass
class _GatedRunner:
    """A runner whose runs all stay in flight until ``release`` is set."""

    release: asyncio.Event = field(default_factory=asyncio.Event)
    in_flight: int = 0
    peak: int = 0
    finished: int = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await self.release.wait()
        finally:
            self.in_flight -= 1
            self.finished += 1
        return JobResult(success=True, output="done")


async def _dispatch_burst(config: CronConfig | None, jobs: int) -> tuple[_GatedRunner, list[asyncio.Task[None]]]:
    store = InMemoryCronStore()
    runner = _GatedRunner()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=config)
    manager = CronManager(store, scheduler)
    snapshots = [
        await manager.create_job(f"job-{index}", JobType.AGENT, EVERY_HOUR, prompt="prompt") for index in range(jobs)
    ]
    tasks = [asyncio.create_task(scheduler._execute_and_persist(job)) for job in snapshots]
    return runner, tasks


async def _wait_until_in_flight(runner: _GatedRunner, count: int) -> None:
    async with asyncio.timeout(5):
        while runner.in_flight < count:
            await asyncio.sleep(0)
    # Give any run over the cap the chance to start, so the count proves it is waiting rather than late.
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.mark.parametrize(
    ("config", "cap"), [(None, DEFAULT_CAP), (CronConfig(max_concurrent=1), 1)], ids=["default", "one"]
)
async def test_a_burst_of_due_jobs_never_runs_more_than_the_cap_at_once(config: CronConfig | None, cap: int) -> None:
    runner, tasks = await _dispatch_burst(config, jobs=cap + 2)

    await _wait_until_in_flight(runner, cap)
    assert runner.in_flight == cap and runner.finished == 0

    runner.release.set()
    await asyncio.gather(*tasks)

    assert runner.peak == cap and runner.finished == cap + 2


async def test_a_waiting_job_takes_the_slot_a_finished_run_frees() -> None:
    runner, tasks = await _dispatch_burst(CronConfig(max_concurrent=1), jobs=2)
    await _wait_until_in_flight(runner, 1)

    runner.release.set()
    await asyncio.gather(*tasks)

    assert runner.finished == 2 and runner.peak == 1
