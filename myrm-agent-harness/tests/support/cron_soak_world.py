"""The world the cron invariants soak runs in: the schedules it draws from and a runner that can hold runs in flight.

[INPUT]
- toolkits.cron.types::ActiveHours, CronJob, JobResult, Schedule, ScheduleKind (POS: Cron job domain types.)

[OUTPUT]
- KINDS / schedule_of / is_fast / closed_window / as_utc / kept_by_a_manual_run: the schedule kinds a soak creates and the questions it asks of them
- Runner: succeeds at once, or holds every run on a gate, and records each run of a job that began while another run of the same job was live

[POS]
Pytest-only helper of the cron invariants soak: the soak keeps the random operations and the invariants, this module the
fake world they run in.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.cron.types import ActiveHours, CronJob, JobResult, Schedule, ScheduleKind

KINDS = ("fast_interval", "hourly_interval", "five_field_cron", "six_field_cron", "once")


def as_utc(moment: datetime | None) -> datetime | None:
    """A store may hand timestamps back naive; they are UTC either way."""
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def is_fast(schedule: Schedule) -> bool:
    """Whether the schedule can fire faster than once a minute."""
    if schedule.kind == ScheduleKind.INTERVAL:
        return (schedule.interval_ms or 0) < 60_000
    return schedule.kind == ScheduleKind.CRON and len((schedule.expr or "").split()) != 5


def schedule_of(kind: str, now: datetime) -> Schedule:
    return {
        "fast_interval": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=1000),
        "hourly_interval": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        # Hourly, half an hour from now: a slot of its own never falls inside a soak, which only injects the slots it checks.
        "five_field_cron": Schedule(kind=ScheduleKind.CRON, expr=f"{(now.minute + 30) % 60} * * * *", stagger_ms=0),
        "six_field_cron": Schedule(kind=ScheduleKind.CRON, expr="*/5 * * * * *", stagger_ms=0),
        "once": Schedule(kind=ScheduleKind.ONCE, run_at=now + timedelta(hours=1)),
    }[kind]


def closed_window(now: datetime) -> ActiveHours:
    """A window that opens in two hours: no moment of the soak falls inside it."""
    return ActiveHours(
        start=(now + timedelta(hours=2)).strftime("%H:%M"), end=(now + timedelta(hours=3)).strftime("%H:%M")
    )


def kept_by_a_manual_run(job: CronJob) -> tuple[object, ...]:
    """What a manual run leaves as it is: the schedule, the status, the next slot and the counters."""
    return (job.schedule, job.status, job.next_run_at, job.fire_count, job.consecutive_failures)


class Runner:
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
