"""Random-operation soak of the cron protocol on the SQLAlchemy store.

Eight seeds drive a real ``CronScheduler`` and ``CronManager`` through random operations: a slot comes due, a slot
arrives long after its grace, a second slot of one job arrives while its first run is still in flight, a post-run
write fails, and pause, resume, reschedule, delete and restart, also with a run in flight: a graceful stop cuts it
short, a crash ends the process without a stop. Nothing waits for the clock: a slot comes due by rewriting the stored
``next_run_at`` and the test ticks the scheduler itself. After every step the scheduler is drained, and these
invariants must hold at that quiet point:

- an enabled job has a next run time
- a slot that came due left a run record behind: a run, or a skip
- a job's scheduled runs never overlap
- a schedule that can fire faster than once a minute is booked at least a minute ahead
- no run leaves its in-flight marker behind, and while a run is in flight its marker is the only one
- a stop counts no failure for the run it cut short, and a crash is reported exactly once

Runtime: about 20 s for the eight seeds.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronConfig,
    CronJob,
    CronJobPatch,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import policy_database

_SEEDS = range(1, 9)
_STEPS = 100
_MIN_ACTIVE = 4
_MAX_RECORDS = 100_000
_NO_TIMER_S = 3600.0
_WAIT_S = 30
_FLOOR = timedelta(seconds=59)  # the 60 s floor, less the second a step may take
_GRACE_MISS = timedelta(hours=1)  # misfire grace is five minutes
_KINDS = ("fast_interval", "hourly_interval", "five_field_cron", "six_field_cron", "once")
_OPS = {
    "slot": 38,
    "late_slot": 6,
    "overlap": 8,
    "closer_fail": 10,
    "pause": 9,
    "resume": 9,
    "reschedule": 8,
    "delete": 4,
    "restart": 4,
    "stop_busy": 3,
    "crash": 3,
}


def _utc(moment: datetime | None) -> datetime | None:
    """A store may hand timestamps back naive; they are UTC either way."""
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def _fast(schedule: Schedule) -> bool:
    if schedule.kind == ScheduleKind.INTERVAL:
        return (schedule.interval_ms or 0) < 60_000
    return schedule.kind == ScheduleKind.CRON and len((schedule.expr or "").split()) != 5


def _schedule(kind: str, now: datetime) -> Schedule:
    return {
        "fast_interval": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=1000),
        "hourly_interval": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        "five_field_cron": Schedule(kind=ScheduleKind.CRON, expr="*/10 * * * *", stagger_ms=0),
        "six_field_cron": Schedule(kind=ScheduleKind.CRON, expr="*/5 * * * * *", stagger_ms=0),
        "once": Schedule(kind=ScheduleKind.ONCE, run_at=now + timedelta(hours=1)),
    }[kind]


def _closed_window(now: datetime) -> ActiveHours:
    """A window that opens in two hours: no moment of this test falls inside it."""
    return ActiveHours(start=(now + timedelta(hours=2)).strftime("%H:%M"), end=(now + timedelta(hours=3)).strftime("%H:%M"))


class _Runner:
    """Succeeds at once; while ``gate`` is set every run waits on it, so a run stays in flight across a tick."""

    def __init__(self) -> None:
        self.gate: asyncio.Event | None = None
        self.parked: set[asyncio.Task[object]] = set()  # runs waiting on the gate
        self.live: Counter[str] = Counter()
        self.overlaps: list[str] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.live[job.id] += 1
        if self.live[job.id] > 1:
            self.overlaps.append(job.id)
        task = asyncio.current_task()
        assert task is not None
        try:
            if self.gate:
                self.parked.add(task)
                await self.gate.wait()
            else:
                await asyncio.sleep(0)
        finally:
            self.parked.discard(task)
            self.live[job.id] -= 1
        return JobResult(success=True, output="ok")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _Soak:
    def __init__(self, seed: int, store: SqlAlchemyCronStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self.seed = seed
        self.rnd = random.Random(seed)
        self.store = store
        self.runner = _Runner()
        self.order: list[str] = []  # creation order keeps the choices reproducible
        self.plain: set[str] = set()  # outside any window and cooldown: its slots really run
        self.expected: Counter[str] = Counter()  # in-grace slots that came due, per job
        self.injected: dict[str, datetime] = {}
        self.fail_save_for: str | None = None
        self.created = 0
        self.step_no = 0
        self.last_op = ""
        self.violations: dict[tuple[str, str], str] = {}  # first sighting per (invariant, subject)
        self.overlaps_seen = 0
        original = store.save_job

        async def save_job(job: CronJob) -> CronJob:
            if job.id == self.fail_save_for:
                self.fail_save_for = None
                raise RuntimeError("injected: the post-run write failed")
            return await original(job)

        monkeypatch.setattr(store, "save_job", save_job)

    async def start(self) -> None:
        self.runner.gate = None  # a new process holds no run
        self.sched = CronScheduler(
            store=self.store,
            runners={JobType.AGENT: self.runner},
            delivery=_Delivery(),
            config=CronConfig(max_concurrent=20),
        )
        self.mgr = CronManager(store=self.store, scheduler=self.sched)
        await self.sched.start()
        await self._drain()

    async def close(self) -> None:
        if self.runner.gate:
            self.runner.gate.set()
        await self.sched.stop()
        leftovers = self._tasks()
        for task in leftovers:
            task.cancel()
        await asyncio.gather(*leftovers, return_exceptions=True)

    @staticmethod
    def _tasks() -> list[asyncio.Task[object]]:
        me = asyncio.current_task()
        return [task for task in asyncio.all_tasks() if task is not me and not task.done()]

    async def _drain(self) -> None:
        """Wait for every task the scheduler spawned: nothing else runs on this loop."""
        async with asyncio.timeout(_WAIT_S):
            while pending := self._tasks():
                await asyncio.gather(*pending, return_exceptions=True)

    async def _drain_but_parked(self) -> None:
        async with asyncio.timeout(_WAIT_S):
            while any(task not in self.runner.parked for task in self._tasks()):
                await asyncio.sleep(0)

    async def _jobs(self, *statuses: JobStatus) -> list[CronJob]:
        by_id = {job.id: job for job in await self.store.list_jobs()}
        return [by_id[i] for i in self.order if i in by_id and (not statuses or by_id[i].status in statuses)]

    async def _pick(self, *statuses: JobStatus, plain: bool = False) -> CronJob | None:
        jobs = [job for job in await self._jobs(*statuses) if not plain or job.id in self.plain]
        return self.rnd.choice(jobs) if jobs else None

    async def _create(self) -> None:
        now = datetime.now(UTC)
        kind = self.rnd.choice(_KINDS)
        closed = kind != "once" and self.rnd.random() < 0.2
        cooldown = 30 if kind != "once" and self.rnd.random() < 0.25 else 0
        self.created += 1
        job = await self.mgr.create_job(
            f"{kind}-{self.created}",
            JobType.AGENT,
            _schedule(kind, now),
            prompt="x",
            model="m",
            active_hours=_closed_window(now) if closed else None,
            cooldown_seconds=cooldown,
            delete_after_run=False,
        )
        self.order.append(job.id)
        if not closed and not cooldown:
            self.plain.add(job.id)

    async def _make_due(self, job: CronJob, age: timedelta = timedelta(seconds=1)) -> None:
        stored = await self.store.get_job(job.id)
        assert stored is not None
        stored.next_run_at = datetime.now(UTC) - age
        await self.store.save_job(stored)
        self.injected[job.id] = stored.next_run_at

    async def _tick(self) -> None:
        await self.sched._on_tick()
        await self._drain()

    # -- operations -----------------------------------------------------------------------------------------------

    async def op_slot(self) -> None:
        jobs = await self._jobs(JobStatus.ACTIVE)
        for job in self.rnd.sample(jobs, k=min(len(jobs), self.rnd.choice((1, 1, 2)))):
            await self._make_due(job)
            self.expected[job.id] += 1
        await self._tick()

    async def op_late_slot(self) -> None:
        if job := await self._pick(JobStatus.ACTIVE):
            await self._make_due(job, _GRACE_MISS)
            await self._tick()

    async def _hold_run_of(self, job: CronJob) -> asyncio.Event:
        """Start a run of the job and keep it in flight until the returned gate is set."""
        gate = asyncio.Event()
        self.runner.gate = gate
        await self._make_due(job)
        self.expected[job.id] += 1
        await self.sched._on_tick()
        async with asyncio.timeout(_WAIT_S):  # other due jobs start in the same tick: wait for this job's own run
            while not self.runner.live[job.id]:
                await asyncio.sleep(0.001)
        return gate

    async def op_overlap(self) -> None:
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        gate = await self._hold_run_of(job)
        await self._make_due(job)  # a second slot while the first run is still in flight
        await self.sched._on_tick()
        await self._drain_but_parked()
        if (markers := [job_id for job_id, _ in await self.store.list_running()]) != [job.id]:
            self._violate("marker", job.name, f"has one run in flight and the markers are {markers}")
        gate.set()
        self.runner.gate = None
        await self._drain()

    async def op_stop_busy(self) -> None:
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        await self._hold_run_of(job)
        await self.sched.stop()
        await self.start()
        if (after := await self.store.get_job(job.id)) and after.consecutive_failures > job.consecutive_failures:
            self._violate("stop", job.name, "counted a failure for the run the stop cut short")

    async def _reports(self, job: CronJob) -> int:
        runs = await self.store.list_runs(job.id, limit=_MAX_RECORDS)
        return sum(run.trigger_source == "recovery" for run in runs)

    async def op_crash(self) -> None:
        """The process ends with a run in flight: its tasks die, nothing is written, the restart reports the run."""
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        reported = await self._reports(job)
        await self._hold_run_of(job)
        victims = self._tasks()
        for task in victims:
            task.cancel()
        await asyncio.gather(*victims, return_exceptions=True)
        await self.start()
        if (now := await self._reports(job)) != reported + 1:
            self._violate("crash", job.name, f"has {now - reported} interrupted-run records after a crash, expected 1")

    async def op_closer_fail(self) -> None:
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        await self._make_due(job)
        self.expected[job.id] += 1
        self.fail_save_for = job.id
        await self._tick()
        self.fail_save_for = None

    async def op_pause(self) -> None:
        if job := await self._pick(JobStatus.ACTIVE):
            await self.mgr.pause_job(job.id)

    async def op_resume(self) -> None:
        if job := await self._pick(JobStatus.PAUSED):
            with contextlib.suppress(ValueError):  # a refusal changes nothing
                await self.mgr.resume_job(job.id)

    async def op_reschedule(self) -> None:
        if job := await self._pick():
            patch = CronJobPatch(schedule=_schedule(self.rnd.choice(_KINDS), datetime.now(UTC)))
            with contextlib.suppress(ValueError):
                await self.mgr.update_job(job.id, patch)

    async def op_delete(self) -> None:
        if job := await self._pick():
            await self.mgr.delete_job(job.id)
            self.order.remove(job.id)
            self.expected.pop(job.id, None)

    async def op_restart(self) -> None:
        await self.sched.stop()
        await self.start()

    # -- invariants -----------------------------------------------------------------------------------------------

    def _violate(self, invariant: str, subject: str, detail: str) -> None:
        self.violations.setdefault((invariant, subject), f"step {self.step_no}, {self.last_op}: {subject} {detail}")

    async def check(self, started: datetime, before: dict[str, datetime | None]) -> None:
        jobs = await self._jobs()
        records = Counter(run.job_id for run in await self.store.list_runs(limit=_MAX_RECORDS))
        for job in jobs:
            if job.status == JobStatus.ACTIVE and job.next_run_at is None:
                self._violate("next-run", job.name, "is enabled without a next run time")
            have = records[job.id]
            if have < self.expected[job.id]:
                self._violate("record", job.name, f"came due {self.expected[job.id]}x and has {have} run records")
            booked = _utc(job.next_run_at)
            if job.status != JobStatus.ACTIVE or booked is None or not _fast(job.schedule):
                continue
            if booked not in (before.get(job.id), self.injected.get(job.id)) and booked - started < _FLOOR:
                self._violate("floor", job.name, f"is booked only {booked - started} ahead")
        if left := [job_id for job_id, _ in await self.store.list_running()]:
            self._violate("marker", ",".join(left), "kept an in-flight marker after its run ended")
        if len(self.runner.overlaps) > self.overlaps_seen:
            self._violate("overlap", ",".join(self.runner.overlaps[self.overlaps_seen :]), "ran twice at once")
            self.overlaps_seen = len(self.runner.overlaps)

    def verdict(self) -> None:
        if not self.violations:
            return
        raise AssertionError(f"seed {self.seed}: {len(self.violations)} violations\n" + "\n".join(self.violations.values()))

    async def step(self) -> None:
        for _ in range(_MIN_ACTIVE - len(await self._jobs(JobStatus.ACTIVE))):
            await self._create()
        op = self.rnd.choices(list(_OPS), weights=list(_OPS.values()))[0]
        before = {job.id: _utc(job.next_run_at) for job in await self._jobs()}
        self.injected.clear()
        self.step_no += 1
        self.last_op = op
        started = datetime.now(UTC)
        await getattr(self, f"op_{op}")()
        await self.check(started, before)


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test ticks the scheduler itself; its own timers must never fire in between."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, _NO_TIMER_S)


@pytest_asyncio.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SqlAlchemyCronStore]:
    async with policy_database(tmp_path / "cron.db", monkeypatch):
        yield SqlAlchemyCronStore()


@pytest.mark.parametrize("seed", _SEEDS)
async def test_invariants_hold_after_every_step(seed: int, store: SqlAlchemyCronStore, monkeypatch: pytest.MonkeyPatch) -> None:
    soak = _Soak(seed, store, monkeypatch)
    await soak.start()
    try:
        for _ in range(_STEPS):
            await soak.step()
    finally:
        await soak.close()
    soak.verdict()
