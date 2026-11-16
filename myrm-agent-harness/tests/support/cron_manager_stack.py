"""A real cron manager over the in-memory store, for tests that drive the manager and the agent tool end to end.

[INPUT]
- toolkits.cron::CronConfig, CronManager, CronScheduler (POS: the manager, the scheduler it notifies and the engine config)
- toolkits.cron.protocols::CronNoticeCallback, JobRunner (POS: the runner and notice callback a test may inject)
- toolkits.cron.stores::InMemoryCronStore (POS: job and run persistence without a database)

[OUTPUT]
- ManagerStack / make_manager_stack: the store, the manager and the scheduler (never started), with `create`, `stored`,
  `rewrite`, `records` and `settle`; a runner and a notice callback may be injected
- NoDelivery: a delivery that accepts every result and sends nothing

[POS]
Pytest-only helper shared by the cron activation, timezone and manual-run tests: a test states the job and the state it
is in, calls the manager or the `cron_manage` tool, and reads the outcome back from the store instead of mocking the
manager.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronRunRecord,
    JobResult,
    JobType,
    Schedule,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronNoticeCallback, JobRunner

_SETTLE_PATIENCE_S = 5


class NoDelivery:
    """A delivery that accepts every result and sends nothing."""

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


@dataclass
class ManagerStack:
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler

    async def create(self, name: str, schedule: Schedule, *, active_hours: ActiveHours | None = None) -> CronJob:
        """Create an agent job through the manager, so its first slot is booked the way production books it."""
        return await self.manager.create_job(name, JobType.AGENT, schedule, prompt="prompt", active_hours=active_hours)

    async def stored(self, job_id: str) -> CronJob:
        found = await self.store.get_job(job_id)
        assert found is not None
        return found

    async def records(self, job_id: str) -> list[CronRunRecord]:
        return await self.store.list_runs(job_id)

    async def rewrite(self, job_id: str, **changes: object) -> None:
        """Put the stored job into a state the manager would not produce by itself (an auto-pause, a passed time)."""
        await self.store.save_job(replace(await self.stored(job_id), **changes))  # type: ignore[arg-type]

    async def settle(self) -> None:
        """Wait until no run is in flight, so the closing write of every run has been made."""
        async with asyncio.timeout(_SETTLE_PATIENCE_S):
            while self.scheduler._in_flight:
                await asyncio.sleep(0)


def make_manager_stack(runner: JobRunner | None = None, on_notice: CronNoticeCallback | None = None) -> ManagerStack:
    """The stack; without a ``runner`` no job type has one, so a run that starts ends at once as unrunnable."""
    store = InMemoryCronStore()
    runners = {JobType.AGENT: runner} if runner is not None else {}
    scheduler = CronScheduler(
        store=store, runners=runners, delivery=NoDelivery(), config=CronConfig(), on_notice=on_notice
    )
    return ManagerStack(store, CronManager(store, scheduler), scheduler)
