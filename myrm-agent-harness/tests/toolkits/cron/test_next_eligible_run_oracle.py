"""Slot oracle: ``next_eligible_run`` against an independent enumeration of a schedule's slots.

[INPUT]
- toolkits.cron.engine.helpers::next_eligible_run (POS: pure engine helpers: the next slot to book)
- toolkits.cron.types::ActiveHours, CronJob, Schedule (POS: Cron job domain types.)

[OUTPUT]
- that the slot booked for a job is the first one after its cooldown and 60 s floor that lies in its active window,
  across schedule kinds, time zones (the days around New York's clock changes included), windows and cooldowns
- that adjacent bookings of a schedule that can fire faster than once a minute are at least 60 s apart (I5)

[POS]
Permanent slot-oracle gate for the one function that derives a job's next regular slot. The oracle shares no code
with the engine: slots are enumerated minute by minute (second by second for a 6-field cron) in ``zoneinfo`` local
time, never through croniter, and window membership is computed from the local clock reading.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import pytest

from myrm_agent_harness.toolkits.cron.engine.helpers import next_eligible_run
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

_FLOOR = timedelta(seconds=60)
_SCAN_BOUND = 2000
_ZONES = ("UTC", "Asia/Shanghai", "America/New_York")
_WINDOWS: dict[str, tuple[str, str] | None] = {"none": None, "night": ("22:00", "06:00"), "day": ("09:00", "18:00")}

# Ordinary instants, an exact minute boundary, and the days before and after New York's 2026-03-08 and 2026-11-01
# clock changes.
_AFTERS = (
    datetime(2026, 1, 15, 3, 7, 42, 250_000, tzinfo=UTC),
    datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC),
    datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
    datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
    datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
)
# The clock-change days themselves: only an interval is asserted there, a cron's behavior on them is left as it is.
_CLOCK_CHANGE_AFTERS = (datetime(2026, 3, 8, 6, 30, tzinfo=UTC), datetime(2026, 11, 1, 5, 30, tzinfo=UTC))


def _cron(expr: str) -> Callable[[str], Schedule]:
    return lambda zone: Schedule(kind=ScheduleKind.CRON, expr=expr, tz=zone)


def _interval(ms: int) -> Callable[[str], Schedule]:
    return lambda _zone: Schedule(kind=ScheduleKind.INTERVAL, interval_ms=ms)


@dataclass(frozen=True)
class _Case:
    name: str
    schedule: Callable[[str], Schedule]
    windows: tuple[str, ...]
    cooldown_seconds: int  # longer than the schedule's own gap, so that it decides the earliest slot
    interval_based: bool = False


# A daily or weekday rule meets only windows that contain its slot: the oracle looks for the slot minute by minute.
_CASES = (
    _Case("cron5-every-5-minutes", _cron("*/5 * * * *"), ("none", "night", "day"), 900),
    _Case("cron5-hourly-at-15", _cron("15 * * * *"), ("none", "night", "day"), 7200),
    _Case("cron5-daily-0930", _cron("30 9 * * *"), ("none", "day"), 90_000),
    _Case("cron5-weekdays-0900", _cron("0 9 * * 1-5"), ("none", "day"), 100_000),
    _Case("cron6-every-20-seconds", _cron("* * * * * */20"), ("none", "day"), 300),
    _Case("cron6-every-5-minutes", _cron("*/5 * * * * 0"), ("none", "night", "day"), 900),
    _Case("interval-1-second", _interval(1000), ("none", "day"), 300, interval_based=True),
    _Case("interval-90-seconds", _interval(90_000), ("none", "night", "day"), 600, interval_based=True),
    _Case("interval-1-hour", _interval(3_600_000), ("none", "night", "day"), 7200, interval_based=True),
)


@dataclass(frozen=True)
class _CompiledCron:
    zone: ZoneInfo
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]  # Sunday is 0
    seconds: frozenset[int] | None  # the sixth field, when there is one


def _allowed(spec: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for part in spec.split(","):
        body, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if body == "*":
            first, last = low, high
        elif "-" in body:
            first_text, last_text = body.split("-")
            first, last = int(first_text), int(last_text)
        else:
            first = last = int(body)
        values.update(range(first, last + 1, step))
    return frozenset(values)


@cache
def _compile(expr: str, zone: str | None) -> _CompiledCron:
    fields = expr.split()
    minute, hour, day, month, weekday = fields[:5]
    assert day == "*" or weekday == "*", "the oracle does not model cron's day-of-month OR day-of-week rule"
    return _CompiledCron(
        zone=ZoneInfo(zone or "UTC"),
        minutes=_allowed(minute, 0, 59),
        hours=_allowed(hour, 0, 23),
        days_of_month=_allowed(day, 1, 31),
        months=_allowed(month, 1, 12),
        days_of_week=_allowed(weekday, 0, 6),
        seconds=_allowed(fields[5], 0, 59) if len(fields) == 6 else None,
    )


def _slot_after(schedule: Schedule, moment: datetime) -> datetime:
    """The first slot strictly after ``moment``."""
    if schedule.kind is ScheduleKind.INTERVAL:
        return moment + timedelta(milliseconds=schedule.interval_ms or 0)
    cron = _compile(schedule.expr or "", schedule.tz)
    step = timedelta(seconds=1) if cron.seconds is not None else timedelta(minutes=1)
    current = moment.replace(microsecond=0) if cron.seconds is not None else moment.replace(second=0, microsecond=0)
    while True:
        current += step
        local = current.astimezone(cron.zone)
        if (
            local.minute in cron.minutes
            and local.hour in cron.hours
            and local.day in cron.days_of_month
            and local.month in cron.months
            and (local.weekday() + 1) % 7 in cron.days_of_week
            and (cron.seconds is None or local.second in cron.seconds)
        ):
            return current


def _in_window(hours: ActiveHours | None, moment: datetime) -> bool:
    if hours is None:
        return True
    local = moment.astimezone(ZoneInfo(hours.tz))
    start = tuple(int(part) for part in hours.start.split(":"))
    end = tuple(int(part) for part in hours.end.split(":"))
    reading = (local.hour, local.minute)
    return start <= reading < end if start < end else reading >= start or reading < end


def _can_fire_within_a_minute(schedule: Schedule) -> bool:
    return schedule.kind is ScheduleKind.INTERVAL or len((schedule.expr or "").split()) != 5


@dataclass(frozen=True)
class _Expected:
    slot: datetime | None
    exhausted: bool  # no slot inside the window within the scan bound


def _expected(job: CronJob, after: datetime, last_run_at: datetime | None) -> _Expected:
    schedule = job.schedule
    if schedule.kind is ScheduleKind.ONCE:
        assert schedule.run_at is not None
        return _Expected(schedule.run_at if schedule.run_at > after else None, exhausted=False)
    earliest = after
    if job.cooldown_seconds > 0 and last_run_at is not None:
        earliest = max(after, last_run_at + timedelta(seconds=job.cooldown_seconds))
    candidate = _slot_after(schedule, earliest)
    if _can_fire_within_a_minute(schedule):
        floor = earliest + _FLOOR
        if candidate < floor:
            candidate = floor if schedule.kind is ScheduleKind.INTERVAL else _slot_after(schedule, floor)
    for _ in range(_SCAN_BOUND):
        if _in_window(job.active_hours, candidate):
            return _Expected(candidate, exhausted=False)
        candidate = _slot_after(schedule, candidate)
    return _Expected(None, exhausted=True)


def _job(schedule: Schedule, window: tuple[str, str] | None = None, zone: str = "UTC", cooldown: int = 0) -> CronJob:
    return CronJob(
        id="job",
        name="job",
        job_type=JobType.AGENT,
        schedule=schedule,
        status=JobStatus.ACTIVE,
        prompt="p",
        delivery=DeliveryConfig(channel="none"),
        active_hours=ActiveHours(start=window[0], end=window[1], tz=zone) if window else None,
        cooldown_seconds=cooldown,
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_the_booked_slot_is_the_first_one_the_oracle_finds(case: _Case) -> None:
    afters = _AFTERS + (_CLOCK_CHANGE_AFTERS if case.interval_based else ())
    mismatches: list[str] = []
    checked = 0
    for zone, window_name, cooldown, after in itertools.product(
        _ZONES, case.windows, (0, case.cooldown_seconds), afters
    ):
        job = _job(case.schedule(zone), _WINDOWS[window_name], zone, cooldown)
        last_run_at = after - timedelta(seconds=30)
        expected = _expected(job, after, last_run_at)
        actual = next_eligible_run(job, after, last_run_at=last_run_at)
        checked += 1
        label = f"{zone} window={window_name} cooldown={cooldown} after={after.isoformat()}"
        if expected.exhausted:
            if actual is None or _in_window(job.active_hours, actual):
                mismatches.append(f"{label}: no slot reaches the window, got {actual}")
        elif actual != expected.slot:
            mismatches.append(f"{label}: expected {expected.slot}, got {actual}")
    assert checked > 0
    assert not mismatches, "\n".join(mismatches[:10])


@pytest.mark.parametrize(
    "schedule",
    [
        Schedule(kind=ScheduleKind.INTERVAL, interval_ms=1000),
        Schedule(kind=ScheduleKind.INTERVAL, interval_ms=15_000),
        Schedule(kind=ScheduleKind.CRON, expr="* * * * * */20", tz="UTC"),
        Schedule(kind=ScheduleKind.CRON, expr="*/5 * * * * *", tz="UTC"),
        Schedule(kind=ScheduleKind.CRON, expr="* * * * *", tz="Asia/Shanghai"),
    ],
    ids=["interval-1s", "interval-15s", "cron6-every-20s", "cron6-every-5s", "cron5-every-minute"],
)
@pytest.mark.parametrize("run_seconds", [0, 10])
def test_adjacent_bookings_are_at_least_a_minute_apart(schedule: Schedule, run_seconds: int) -> None:
    job = _job(schedule)
    moment = _AFTERS[0]
    previous: datetime | None = None
    for _ in range(30):
        slot = next_eligible_run(job, moment, last_run_at=moment)
        assert slot is not None
        if previous is not None:
            assert slot - previous >= _FLOOR, f"{previous} then {slot}"
        previous = slot
        moment = slot + timedelta(seconds=run_seconds)  # the run closes after its slot


def test_a_window_no_slot_reaches_yields_a_slot_outside_it() -> None:
    job = _job(Schedule(kind=ScheduleKind.CRON, expr="30 9 * * *", tz="UTC"), ("22:00", "06:00"))

    slot = next_eligible_run(job, _AFTERS[0])

    assert slot is not None
    assert not _in_window(job.active_hours, slot)


@pytest.mark.parametrize("cooldown", [0, 86_400])
def test_a_one_shot_names_its_own_instant(cooldown: int) -> None:
    run_at = datetime(2026, 2, 1, 3, 0, tzinfo=UTC)
    job = _job(Schedule(kind=ScheduleKind.ONCE, run_at=run_at), ("09:00", "18:00"), cooldown=cooldown)

    assert next_eligible_run(job, run_at - timedelta(hours=1), last_run_at=run_at - timedelta(minutes=1)) == run_at
    assert next_eligible_run(job, run_at + timedelta(seconds=1)) is None
