"""A real cron scheduler over the in-memory store whose runs a test holds in flight.

[INPUT]
- toolkits.cron::CronConfig, CronScheduler (POS: the engine under test and its config)
- toolkits.cron.stores::InMemoryCronStore (POS: job, run and in-flight marker persistence without a database)

[OUTPUT]
- InflightStack / make_inflight_stack: the store, a runner that holds every run on a gate and the scheduler, with `add`,
  `launch`, `drain`, `markers`, `interrupted` and `end_runs`
- GateRunner: a runner that waits on a gate and records what the store held when a run was cancelled
- EventLock: a lock that is free or taken and appends to a shared event list when released
- SlowClearStore: a store whose marker deletion waits on a gate
- YieldingStore: a store whose run-record write gives the event loop a turn first, as the I/O of a real store does
- HOURLY, ONCE, CRASHED, STOPPING: the schedules and the two interrupted-run messages

[POS]
Pytest-only helper shared by the in-flight marker and graceful-stop tests: a test states the job and the moment in
the run it cares about, and reads the markers and run records back from the store instead of mocking the scheduler.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.cron import CronConfig, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import CronJob, CronRunRecord, JobResult, JobType, Schedule, ScheduleKind
from tests.support.cron_manager_stack import NoDelivery

HOURLY = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
ONCE = Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) - timedelta(seconds=1))
CRASHED = "Interrupted: the server stopped before this run finished"
STOPPING = "Interrupted: the application was stopping before this run finished"
PATIENCE_S = 10


class GateRunner:
    """Holds every run on ``gate``; on a cancel it notes how many run records the store held, then unwinds."""

    def __init__(self, store: InMemoryCronStore) -> None:
        self.store = store
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.runs = 0
        self.unwind_s = 0.0
        self.records_when_cancelled: list[int] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.runs += 1
        self.entered.set()
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            self.records_when_cancelled.append(len(await self.store.list_runs(job.id)))
            await asyncio.sleep(self.unwind_s)
            raise
        return JobResult(success=True, output="ok")


class EventLock:
    """The scheduler lock: ``free`` decides whether ``try_acquire`` wins; a release is appended to ``events``."""

    def __init__(self, events: list[str], *, free: bool = True) -> None:
        self.events = events
        self.free = free

    async def try_acquire(self, name: str, ttl_seconds: int = 60) -> bool:
        return self.free

    async def release(self, name: str) -> None:
        self.events.append("lock released")


class SlowClearStore(InMemoryCronStore):
    """A store whose marker deletion waits on ``clear_gate``, to cancel a run while its marker is being cleared."""

    def __init__(self) -> None:
        super().__init__()
        self.clearing = asyncio.Event()
        self.clear_gate = asyncio.Event()

    async def clear_running(self, job_id: str) -> None:
        self.clearing.set()
        await self.clear_gate.wait()
        await super().clear_running(job_id)


class YieldingStore(InMemoryCronStore):
    """A store whose run-record write gives the event loop a turn first, as the I/O of a real store does.

    The in-memory store never yields, so a stop that cancels the runs before it writes their records would still look
    as if the records came first: the cancelled tasks only run once the write is over.
    """

    async def save_run(self, run: CronRunRecord) -> None:
        await asyncio.sleep(0)
        await super().save_run(run)


@dataclass
class InflightStack:
    store: InMemoryCronStore
    runner: GateRunner
    scheduler: CronScheduler

    async def add(
        self,
        job_id: str = "job-1",
        schedule: Schedule = HOURLY,
        *,
        due: timedelta = timedelta(seconds=1),
        **fields: object,
    ) -> CronJob:
        """Store an enabled job whose slot came due ``due`` ago; it is not booked, as a job a run is cut short of is not."""
        job = CronJob(
            id=job_id,
            name=f"job {job_id}",
            job_type=JobType.AGENT,
            schedule=schedule,
            prompt="prompt",
            next_run_at=datetime.now(UTC) - due,
            **fields,  # type: ignore[arg-type]
        )
        return await self.store.save_job(job)

    async def stored(self, job_id: str = "job-1") -> CronJob:
        found = await self.store.get_job(job_id)
        assert found is not None
        return found

    async def markers(self) -> list[str]:
        return [job_id for job_id, _ in await self.store.list_running()]

    async def interrupted(self, job_id: str = "job-1") -> list[tuple[str | None, str | None]]:
        """Trigger source and error text of every run record of the job, newest first."""
        return [(run.trigger_source, run.error) for run in await self.store.list_runs(job_id)]

    async def launch(self, job: CronJob, **options: str) -> None:
        """Start a run the way a trigger does and wait until the runner holds it."""
        self.runner.entered.clear()
        self.scheduler._launch(job, **options)
        await asyncio.wait_for(self.runner.entered.wait(), timeout=PATIENCE_S)

    async def drain(self) -> None:
        async with asyncio.timeout(PATIENCE_S):
            while self.scheduler._bg_tasks:
                await asyncio.gather(*list(self.scheduler._bg_tasks), return_exceptions=True)

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)

    async def end_runs(self) -> None:
        """Cancel every task the scheduler spawned, the way an event loop that ends does."""
        for task in list(self.scheduler._bg_tasks):
            task.cancel()
        await self.drain()


def make_inflight_stack(store: InMemoryCronStore | None = None, *, lock: EventLock | None = None) -> InflightStack:
    store = store or InMemoryCronStore()
    runner = GateRunner(store)
    scheduler = CronScheduler(
        store, {JobType.AGENT: runner}, NoDelivery(), config=CronConfig(max_concurrent=4), lock=lock
    )
    return InflightStack(store, runner, scheduler)
