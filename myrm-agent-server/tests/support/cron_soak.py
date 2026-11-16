"""The random operations and the invariants of the cron soak, checked on a real scheduler and manager after every step.

[INPUT]
- toolkits.cron.engine.scheduler::CronScheduler (POS: the scheduler under test)
- toolkits.cron.manager::CronManager (POS: the manager the operations go through)
- toolkits.cron.protocols::CronStore (POS: job, run and in-flight marker persistence)
- toolkits.cron.types::CronConfig, CronJob, CronJobPatch, JobStatus, JobType, RunNowOutcome (POS: Cron job domain types.)
- tests.support.cron_soak_world (POS: the fake world: schedules, a runner that can hold runs in flight, a delivery that sends nothing)

[OUTPUT]
- Soak: ``Soak(seed, store, monkeypatch).run(steps)`` takes the steps and fails with every invariant that was violated, together

[POS]
Pytest-only helper of the cron invariants soak over the SQLAlchemy store: a test file picks the store and the seeds, this
module keeps the random operations and the invariants that test's docstring lists.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    CronJobPatch,
    JobStatus,
    JobType,
    RunNowOutcome,
)

from tests.support.cron_soak_world import (
    KINDS,
    NoDelivery,
    Runner,
    as_utc,
    closed_window,
    is_fast,
    kept_by_a_manual_run,
    schedule_of,
)

if TYPE_CHECKING:
    import pytest
    from myrm_agent_harness.toolkits.cron.protocols import CronStore

_MIN_ACTIVE = 4
_MAX_RECORDS = 100_000
_WAIT_S = 30
_FLOOR = timedelta(seconds=59)  # the 60 s floor, less the second a step may take
_GRACE_MISS = timedelta(hours=1)  # misfire grace is five minutes
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
    "manual": 8,
    "manual_busy": 4,
}


class Soak:
    def __init__(self, seed: int, store: CronStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self.seed = seed
        self.rnd = random.Random(seed)
        self.store = store
        self.runner = Runner()
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
        # The soak ticks the scheduler itself: a timer of its own would start runs between two of its operations.
        monkeypatch.setattr(CronScheduler, "_arm_timer", lambda scheduler: None)
        monkeypatch.setattr(CronScheduler, "_arm_watchdog", lambda scheduler, delay=0.0: None)

    async def start(self) -> None:
        self.runner.gate = None  # a new process holds no run
        self.sched = CronScheduler(
            store=self.store,
            runners={JobType.AGENT: self.runner},
            delivery=NoDelivery(),
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
        kind = self.rnd.choice(KINDS)
        closed = kind != "once" and self.rnd.random() < 0.2
        cooldown = 30 if kind != "once" and self.rnd.random() < 0.25 else 0
        self.created += 1
        job = await self.mgr.create_job(
            f"{kind}-{self.created}",
            JobType.AGENT,
            schedule_of(kind, now),
            prompt="x",
            model="m",
            active_hours=closed_window(now) if closed else None,
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

    async def _wait_live(self, job: CronJob) -> None:
        """Wait for the job's own run to reach the runner: other due jobs start in the same tick."""
        async with asyncio.timeout(_WAIT_S):
            while not self.runner.live[job.id]:
                await asyncio.sleep(0.001)

    async def _hold_run_of(self, job: CronJob) -> asyncio.Event:
        """Start a run of the job and keep it in flight until the returned gate is set."""
        gate = asyncio.Event()
        self.runner.gate = gate
        await self._make_due(job)
        self.expected[job.id] += 1
        await self.sched._on_tick()
        await self._wait_live(job)
        return gate

    async def _check_markers_match_runs(self) -> None:
        """With runs parked, the markers are exactly their jobs: the one held, and any slot that came due beside it."""
        in_flight = {job_id for job_id, runs in self.runner.live.items() if runs}
        markers = {job_id for job_id, _ in await self.store.list_running()}
        if markers != in_flight:
            self._violate(
                "marker",
                ",".join(sorted(markers ^ in_flight)),
                f"has runs in flight {sorted(in_flight)} and markers {sorted(markers)}",
            )

    async def _check_manual_refused(self, job: CronJob) -> None:
        if (outcome := await self.mgr.run_now(job.id)) != RunNowOutcome.ALREADY_RUNNING:
            self._violate("manual", job.name, f"was answered {outcome} for a manual request while a run is in flight")

    async def op_overlap(self) -> None:
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        gate = await self._hold_run_of(job)
        await self._make_due(job)  # a second slot while the first run is still in flight
        await self.sched._on_tick()
        await self._check_manual_refused(job)
        await self._drain_but_parked()
        await self._check_markers_match_runs()
        gate.set()
        self.runner.gate = None
        await self._drain()

    async def op_manual(self) -> None:
        """A manual run of an idle job writes its record and the last-run fields, and nothing else."""
        if (job := await self._pick(JobStatus.ACTIVE)) is None:
            return
        before = await self.store.get_job(job.id)
        assert before is not None
        records = await self._count_runs(job, "manual")
        if (outcome := await self.mgr.run_now(job.id)) != RunNowOutcome.STARTED:
            self._violate("manual", job.name, f"was answered {outcome} for a manual request while idle")
            return
        await self._drain()
        after = await self.store.get_job(job.id)
        assert after is not None
        if kept_by_a_manual_run(before) != kept_by_a_manual_run(after):
            self._violate("manual", job.name, "had its schedule, status or counters changed by a manual run")
        if await self._count_runs(job, "manual") != records + 1:
            self._violate("manual", job.name, "did not get exactly one run record for its manual run")

    async def op_manual_busy(self) -> None:
        """A manual run in flight is the job's one run: a second request is refused and a slot that comes due waits."""
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        gate = asyncio.Event()
        self.runner.gate = gate
        if (outcome := await self.mgr.run_now(job.id)) != RunNowOutcome.STARTED:
            self.runner.gate = None
            self._violate("manual", job.name, f"was answered {outcome} for a manual request while idle")
            return
        await self._wait_live(job)
        await self._check_manual_refused(job)
        await self._make_due(job)
        self.expected[job.id] += 1
        await self.sched._on_tick()
        await self._drain_but_parked()
        await self._check_markers_match_runs()
        gate.set()
        self.runner.gate = None
        await self._drain()
        await self._tick()  # the slot that waited for the manual run

    async def op_stop_busy(self) -> None:
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        await self._hold_run_of(job)
        await self.sched.stop()
        await self.start()
        if (after := await self.store.get_job(job.id)) and after.consecutive_failures > job.consecutive_failures:
            self._violate("stop", job.name, "counted a failure for the run the stop cut short")

    async def _count_runs(self, job: CronJob, source: str) -> int:
        runs = await self.store.list_runs(job.id, limit=_MAX_RECORDS)
        return sum(run.trigger_source == source for run in runs)

    async def op_crash(self) -> None:
        """The process ends with a run in flight: its tasks die, nothing is written, the restart reports the run."""
        if (job := await self._pick(JobStatus.ACTIVE, plain=True)) is None:
            return
        reported = await self._count_runs(job, "recovery")
        await self._hold_run_of(job)
        victims = self._tasks()
        for task in victims:
            task.cancel()
        await asyncio.gather(*victims, return_exceptions=True)
        await self.start()
        if (now := await self._count_runs(job, "recovery")) != reported + 1:
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
            patch = CronJobPatch(schedule=schedule_of(self.rnd.choice(KINDS), datetime.now(UTC)))
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
        # A manual run is a trial, not a slot: it must not stand in for the record a slot owes.
        records = Counter(run.job_id for run in await self.store.list_runs(limit=_MAX_RECORDS) if run.trigger_source != "manual")
        for job in jobs:
            if job.status == JobStatus.ACTIVE and job.next_run_at is None:
                self._violate("next-run", job.name, "is enabled without a next run time")
            have = records[job.id]
            if have < self.expected[job.id]:
                self._violate("record", job.name, f"came due {self.expected[job.id]}x and has {have} run records")
            booked = as_utc(job.next_run_at)
            if job.status != JobStatus.ACTIVE or booked is None or not is_fast(job.schedule):
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

    async def run(self, steps: int) -> None:
        """Start a process, take ``steps`` random steps, stop, and fail with every invariant that was violated."""
        await self.start()
        try:
            for _ in range(steps):
                await self.step()
        finally:
            await self.close()
        self.verdict()

    async def step(self) -> None:
        for _ in range(_MIN_ACTIVE - len(await self._jobs(JobStatus.ACTIVE))):
            await self._create()
        op = self.rnd.choices(list(_OPS), weights=list(_OPS.values()))[0]
        before = {job.id: as_utc(job.next_run_at) for job in await self._jobs()}
        self.injected.clear()
        self.step_no += 1
        self.last_op = op
        started = datetime.now(UTC)
        await getattr(self, f"op_{op}")()
        await self.check(started, before)
