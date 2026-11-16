"""A real cron manager over the in-memory store, for tests that drive the manager and the agent tool end to end.

[INPUT]
- toolkits.cron::CronConfig, CronManager, CronScheduler (POS: the manager, the scheduler it notifies and the engine config)
- toolkits.cron.stores::InMemoryCronStore (POS: job and run persistence without a database)

[OUTPUT]
- ManagerStack / make_manager_stack: the store, the manager and the scheduler (never started), with `create`, `stored`
  and `rewrite`
- NoDelivery: a delivery that accepts every result and sends nothing

[POS]
Pytest-only helper shared by the cron activation, timezone and manual-run tests: a test states the job and the state it
is in, calls the manager or the `cron_manage` tool, and reads the outcome back from the store instead of mocking the
manager.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import ActiveHours, CronJob, JobResult, JobType, Schedule


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

    async def rewrite(self, job_id: str, **changes: object) -> None:
        """Put the stored job into a state the manager would not produce by itself (an auto-pause, a passed time)."""
        await self.store.save_job(replace(await self.stored(job_id), **changes))  # type: ignore[arg-type]


def make_manager_stack() -> ManagerStack:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=NoDelivery(), config=CronConfig())
    return ManagerStack(store, CronManager(store, scheduler), scheduler)
