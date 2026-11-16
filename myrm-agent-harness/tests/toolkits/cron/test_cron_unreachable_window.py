"""A job whose active window its schedule never reaches is refused when a user books it, not left asleep for years.

Create, edit and resume book the next slot through one method of the manager. A recurring schedule none of whose runs
falls inside the job's active window (a daily 20:30 job restricted to 09:00 to 18:00) used to be booked years ahead
without a word and never ran; it is now refused with a message that names the way out. A one-shot names its own instant
and the window never restricts it. A schedule that fires every few seconds is not refused, because its slot scan runs
out within hours and the dispatch guards keep skipping and rebooking it. The scenarios drive the real manager over the
in-memory store; the scheduler is never started.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron.engine.helpers import is_within_active_hours
from myrm_agent_harness.toolkits.cron.types import ActiveHours, CronJobPatch, JobStatus, Schedule, ScheduleKind
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

REFUSED = "no run of this schedule falls inside its active hours"

DAYTIME = ActiveHours(start="09:00", end="18:00", tz="UTC")
AFTERNOON = ActiveHours(start="13:00", end="18:00", tz="UTC")
NIGHT = ActiveHours(start="22:00", end="06:00", tz="UTC")
ALL_DAY = ActiveHours(start="09:00", end="09:00", tz="UTC")


def _daily(clock: str) -> Schedule:
    hour, minute = (int(part) for part in clock.split(":"))
    return Schedule(kind=ScheduleKind.CRON, expr=f"{minute} {hour} * * *", tz="UTC")


def _every(interval: timedelta) -> Schedule:
    return Schedule(kind=ScheduleKind.INTERVAL, interval_ms=int(interval.total_seconds() * 1000))


def _window_ahead(hours: int) -> ActiveHours:
    """A one-hour window that opens ``hours`` from now, so no slot of a short or a daily-aligned schedule lies in it."""
    opens = (datetime.now(UTC) + timedelta(hours=hours)).hour
    return ActiveHours(start=f"{opens:02d}:00", end=f"{(opens + 1) % 24:02d}:00", tz="UTC")


@pytest.fixture
def stack() -> ManagerStack:
    return make_manager_stack()


class TestCreate:
    async def test_a_daily_time_outside_the_window_is_refused_and_stores_nothing(self, stack: ManagerStack) -> None:
        with pytest.raises(ValueError, match=REFUSED):
            await stack.create("evening", _daily("20:30"), active_hours=DAYTIME)

        assert await stack.store.list_jobs() == []

    async def test_a_daily_time_inside_the_window_is_booked_at_that_time(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)

        assert job.next_run_at is not None
        assert (job.next_run_at.hour, job.next_run_at.minute) == (12, 30)

    async def test_a_window_across_midnight_is_judged_on_both_sides_of_it(self, stack: ManagerStack) -> None:
        late = await stack.create("late", _daily("23:00"), active_hours=NIGHT)
        assert late.next_run_at is not None and late.next_run_at.hour == 23

        with pytest.raises(ValueError, match=REFUSED):
            await stack.create("noon", _daily("12:00"), active_hours=NIGHT)

    async def test_a_window_whose_ends_coincide_covers_the_whole_day(self, stack: ManagerStack) -> None:
        job = await stack.create("anytime", _daily("20:30"), active_hours=ALL_DAY)

        assert job.next_run_at is not None and job.next_run_at.hour == 20

    async def test_an_interval_that_always_lands_outside_the_window_is_refused(self, stack: ManagerStack) -> None:
        with pytest.raises(ValueError, match=REFUSED):
            await stack.create("daily-drift", _every(timedelta(days=1)), active_hours=_window_ahead(6))

    async def test_a_schedule_that_fires_every_few_seconds_is_not_refused(self, stack: ManagerStack) -> None:
        window = _window_ahead(12)

        job = await stack.create("ticker", _every(timedelta(seconds=10)), active_hours=window)

        assert job.next_run_at is not None
        assert not is_within_active_hours(window, now=job.next_run_at)
        assert job.next_run_at - datetime.now(UTC) < timedelta(days=1)

    async def test_a_one_shot_is_not_restricted_by_the_window(self, stack: ManagerStack) -> None:
        run_at = datetime.now(UTC) + timedelta(days=3)
        job = await stack.create(
            "reminder", Schedule(kind=ScheduleKind.ONCE, run_at=run_at), active_hours=_window_ahead(10)
        )

        assert job.next_run_at == run_at


class TestUpdate:
    async def test_a_window_the_schedule_never_reaches_is_refused_and_the_job_stays_as_it_was(
        self, stack: ManagerStack
    ) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)

        with pytest.raises(ValueError, match=REFUSED):
            await stack.manager.update_job(job.id, CronJobPatch(active_hours=AFTERNOON))

        kept = await stack.stored(job.id)
        assert (kept.active_hours, kept.next_run_at) == (DAYTIME, job.next_run_at)

    async def test_a_schedule_the_window_never_reaches_is_refused(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)

        with pytest.raises(ValueError, match=REFUSED):
            await stack.manager.update_job(job.id, CronJobPatch(schedule=_daily("20:30")))

        assert (await stack.stored(job.id)).schedule == job.schedule

    async def test_a_window_the_schedule_reaches_is_booked_again(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)

        moved = await stack.manager.update_job(job.id, CronJobPatch(schedule=_daily("16:45")))

        assert moved is not None and moved.next_run_at is not None
        assert (moved.next_run_at.hour, moved.next_run_at.minute) == (16, 45)

    async def test_an_edit_that_leaves_the_slot_alone_never_trips_over_an_old_window(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)
        await stack.rewrite(job.id, active_hours=AFTERNOON)  # a window no slot reaches, stored before the rule existed

        renamed = await stack.manager.update_job(job.id, CronJobPatch(name="lunch break"))

        assert renamed is not None and renamed.name == "lunch break"

    async def test_a_paused_job_keeps_its_edits_and_the_resume_is_what_refuses(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)
        await stack.manager.pause_job(job.id)

        edited = await stack.manager.update_job(job.id, CronJobPatch(active_hours=AFTERNOON))
        assert edited is not None and edited.active_hours == AFTERNOON and edited.status == JobStatus.PAUSED

        with pytest.raises(ValueError, match=REFUSED):
            await stack.manager.resume_job(job.id)
        assert (await stack.stored(job.id)).status == JobStatus.PAUSED


class TestResume:
    async def test_a_window_the_schedule_never_reaches_keeps_the_job_paused(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, next_run_at=None, active_hours=AFTERNOON)

        with pytest.raises(ValueError, match=REFUSED):
            await stack.manager.resume_job(job.id)

        stored = await stack.stored(job.id)
        assert (stored.status, stored.next_run_at) == (JobStatus.PAUSED, None)

    async def test_one_patch_that_widens_the_window_and_activates_resumes_the_job(self, stack: ManagerStack) -> None:
        job = await stack.create("lunch", _daily("12:30"), active_hours=DAYTIME)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, next_run_at=None, active_hours=AFTERNOON)

        resumed = await stack.manager.update_job(
            job.id,
            CronJobPatch(status=JobStatus.ACTIVE, active_hours=ActiveHours(start="12:00", end="13:00", tz="UTC")),
        )

        assert resumed is not None and resumed.status == JobStatus.ACTIVE
        assert resumed.next_run_at is not None and resumed.next_run_at.hour == 12
