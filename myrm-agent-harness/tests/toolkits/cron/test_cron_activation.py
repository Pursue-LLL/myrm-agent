"""A one-shot's time must lie ahead, and a re-enabled job gets a fresh slot and a fresh failure record.

The manager owns the rules: a one-time schedule whose instant has passed is rejected on create and on update, and a
job that is not enabled becomes enabled again only through one path. ``resume_job`` and an ``update_job`` that carries
``status=ACTIVE`` share it, so both check the job as the patch leaves it, reset the failure count, the last error and
the reason the scheduler paused the job, and book the next slot; an enabled job comes back from a resume untouched.
Any other status a person sets replaces the scheduler's pause and its reason. An enabled job whose schedule, cooldown
or active window changes books its slot again. These scenarios drive the real manager, the in-memory store and the
``cron_manage`` tool; nothing is mocked, and the scheduler is never started.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.heartbeat import enable_heartbeat
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronJobPatch,
    JobStatus,
    PauseReason,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000)

PASSED_ON_CREATE = "its scheduled time has passed; choose a future time"
PASSED_ON_RESUME = "its scheduled time has passed; set a new time before resuming"


@pytest.fixture
def stack() -> ManagerStack:
    return make_manager_stack()


def _once(offset: timedelta) -> Schedule:
    return Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + offset)


def _window_ahead(hours: int) -> tuple[ActiveHours, int]:
    """A one-hour active window that opens ``hours`` from now, and the hour it opens at (UTC)."""
    opens = (datetime.now(UTC) + timedelta(hours=hours)).hour
    return ActiveHours(start=f"{opens:02d}:00", end=f"{(opens + 1) % 24:02d}:00", tz="UTC"), opens


class TestOneShotTimeMustLieAhead:
    async def test_create_in_the_past_is_rejected_and_stores_nothing(self, stack: ManagerStack) -> None:
        with pytest.raises(ValueError, match=PASSED_ON_CREATE):
            await stack.create("late", _once(-HOUR))
        assert await stack.store.list_jobs() == []

    async def test_a_naive_time_is_read_as_utc(self, stack: ManagerStack) -> None:
        past = (datetime.now(UTC) - HOUR).replace(tzinfo=None)
        with pytest.raises(ValueError, match=PASSED_ON_CREATE):
            await stack.create("naive-late", Schedule(kind=ScheduleKind.ONCE, run_at=past))
        ahead = (datetime.now(UTC) + HOUR).replace(tzinfo=None)
        job = await stack.create("naive-ahead", Schedule(kind=ScheduleKind.ONCE, run_at=ahead))
        assert job.next_run_at == ahead.replace(tzinfo=UTC)

    async def test_create_ahead_books_the_named_instant(self, stack: ManagerStack) -> None:
        schedule = _once(HOUR)
        job = await stack.create("soon", schedule)
        assert job.next_run_at == schedule.run_at

    async def test_update_to_the_past_is_rejected_and_the_job_stays_as_it_was(self, stack: ManagerStack) -> None:
        job = await stack.create("soon", _once(DAY))
        with pytest.raises(ValueError, match=PASSED_ON_CREATE):
            await stack.manager.update_job(job.id, CronJobPatch(schedule=_once(-HOUR)))
        kept = await stack.stored(job.id)
        assert kept.schedule == job.schedule
        assert kept.next_run_at == job.next_run_at


class TestResumingAnOneShot:
    async def test_a_time_that_has_passed_is_rejected_and_the_job_stays_paused(self, stack: ManagerStack) -> None:
        job = await stack.create("call-mom", _once(HOUR))
        await stack.manager.pause_job(job.id)
        await stack.rewrite(job.id, schedule=_once(-HOUR))  # the reminder time passes while the job is paused
        with pytest.raises(ValueError, match=PASSED_ON_RESUME):
            await stack.manager.resume_job(job.id)
        assert (await stack.stored(job.id)).status == JobStatus.PAUSED

    async def test_a_time_still_ahead_is_booked_as_it_is(self, stack: ManagerStack) -> None:
        schedule = _once(HOUR)
        job = await stack.create("call-mom", schedule)
        await stack.manager.pause_job(job.id)
        resumed = await stack.manager.resume_job(job.id)
        assert resumed is not None
        assert resumed.status == JobStatus.ACTIVE
        assert resumed.next_run_at == schedule.run_at

    async def test_one_patch_that_names_a_new_time_and_activates_resumes_it(self, stack: ManagerStack) -> None:
        job = await stack.create("call-mom", _once(HOUR))
        await stack.manager.pause_job(job.id)
        await stack.rewrite(job.id, schedule=_once(-HOUR))
        new_time = _once(DAY)
        resumed = await stack.manager.update_job(job.id, CronJobPatch(status=JobStatus.ACTIVE, schedule=new_time))
        assert resumed is not None
        assert resumed.status == JobStatus.ACTIVE
        assert resumed.next_run_at == new_time.run_at


async def _resume(stack: ManagerStack, job_id: str) -> CronJob | None:
    return await stack.manager.resume_job(job_id)


async def _patch_to_active(stack: ManagerStack, job_id: str) -> CronJob | None:
    return await stack.manager.update_job(job_id, CronJobPatch(status=JobStatus.ACTIVE))


Activate = Callable[[ManagerStack, str], Awaitable[CronJob | None]]
BOTH_ENTRIES = pytest.mark.parametrize("activate", [_resume, _patch_to_active], ids=["resume_job", "status_patch"])


class TestActivation:
    @BOTH_ENTRIES
    async def test_an_auto_paused_job_gets_a_slot_and_starts_its_failure_story_over(
        self, stack: ManagerStack, activate: Activate
    ) -> None:
        job = await stack.create("flaky", EVERY_HOUR)
        await stack.rewrite(
            job.id,
            status=JobStatus.PAUSED,
            next_run_at=None,
            consecutive_failures=3,
            last_error="boom",
            paused_reason=PauseReason.RUN_FAILURES,
        )

        before = datetime.now(UTC)
        resumed = await activate(stack, job.id)
        after = datetime.now(UTC)

        assert resumed is not None
        assert resumed.status == JobStatus.ACTIVE
        assert resumed.consecutive_failures == 0
        assert (resumed.last_error, resumed.paused_reason) == (None, None)
        assert resumed.next_run_at is not None
        assert before + HOUR <= resumed.next_run_at <= after + HOUR
        assert await stack.stored(job.id) == resumed

    @BOTH_ENTRIES
    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            pytest.param({"status": JobStatus.COMPLETED}, "completed jobs cannot be resumed", id="completed"),
            pytest.param(
                {"expires_at": datetime.now(UTC) - timedelta(minutes=1)},
                "job has expired; extend expires_at before resuming",
                id="expired",
            ),
            pytest.param(
                {"max_fires": 2, "fire_count": 2},
                "max execution count reached; increase max_fires before resuming",
                id="max_fires_reached",
            ),
        ],
    )
    async def test_a_job_that_cannot_run_is_rejected_and_left_as_it_was(
        self, stack: ManagerStack, activate: Activate, changes: dict[str, object], message: str
    ) -> None:
        job = await stack.create("stuck", EVERY_HOUR)
        await stack.rewrite(job.id, **{"status": JobStatus.PAUSED, "next_run_at": None, **changes})
        before = await stack.stored(job.id)

        with pytest.raises(ValueError, match=message):
            await activate(stack, job.id)

        assert await stack.stored(job.id) == before

    async def test_a_patch_that_removes_the_obstacle_activates_in_the_same_call(self, stack: ManagerStack) -> None:
        job = await stack.create("expired", EVERY_HOUR)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        resumed = await stack.manager.update_job(job.id, CronJobPatch(status=JobStatus.ACTIVE, clear_expires_at=True))

        assert resumed is not None
        assert resumed.status == JobStatus.ACTIVE
        assert resumed.expires_at is None
        assert resumed.next_run_at is not None

    async def test_an_activation_wakes_the_scheduler(self, stack: ManagerStack) -> None:
        job = await stack.create("paused", EVERY_HOUR)
        await stack.manager.pause_job(job.id)
        with patch.object(stack.scheduler, "notify_change") as notified:
            await stack.manager.resume_job(job.id)
        notified.assert_called_once_with()

    async def test_resuming_an_enabled_job_changes_nothing(self, stack: ManagerStack) -> None:
        job = await stack.create("busy", EVERY_HOUR)
        await stack.rewrite(job.id, consecutive_failures=2)
        before = await stack.stored(job.id)

        with patch.object(stack.scheduler, "notify_change") as notified:
            returned = await stack.manager.resume_job(job.id)

        assert returned == before
        assert await stack.stored(job.id) == before
        notified.assert_not_called()

    async def test_resuming_an_unknown_job_returns_none(self, stack: ManagerStack) -> None:
        assert await stack.manager.resume_job("missing") is None

    async def test_enabling_a_paused_heartbeat_books_its_next_run(self, stack: ManagerStack) -> None:
        first = await enable_heartbeat(stack.manager)
        await stack.rewrite(
            first.id,
            status=JobStatus.PAUSED,
            next_run_at=None,
            consecutive_failures=3,
            paused_reason=PauseReason.CIRCUIT_BREAK,
        )

        again = await enable_heartbeat(stack.manager)

        assert again.id == first.id
        assert again.status == JobStatus.ACTIVE
        assert again.consecutive_failures == 0
        assert again.paused_reason is None
        assert again.next_run_at is not None

    @pytest.mark.parametrize("status", [JobStatus.PAUSED, JobStatus.COMPLETED], ids=["paused", "completed"])
    async def test_a_status_a_person_sets_replaces_the_pause_the_scheduler_gave(
        self, stack: ManagerStack, status: JobStatus
    ) -> None:
        job = await stack.create("flaky", EVERY_HOUR)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, next_run_at=None, paused_reason=PauseReason.SCHEDULE_ERROR)

        patched = await stack.manager.update_job(job.id, CronJobPatch(status=status))

        assert patched is not None
        assert (patched.status, patched.paused_reason) == (status, None)

    async def test_a_patch_that_leaves_the_status_alone_keeps_the_pause_reason(self, stack: ManagerStack) -> None:
        job = await stack.create("flaky", EVERY_HOUR)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, next_run_at=None, paused_reason=PauseReason.CIRCUIT_BREAK)

        patched = await stack.manager.update_job(job.id, CronJobPatch(name="renamed"))

        assert patched is not None
        assert (patched.status, patched.paused_reason) == (JobStatus.PAUSED, PauseReason.CIRCUIT_BREAK)


class TestEnabledJobBooksAgainWhenASlotInputChanges:
    async def test_a_new_schedule_moves_the_slot(self, stack: ManagerStack) -> None:
        job = await stack.create("hourly", EVERY_HOUR)
        before = datetime.now(UTC)
        updated = await stack.manager.update_job(
            job.id, CronJobPatch(schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=7_200_000))
        )
        after = datetime.now(UTC)
        assert updated is not None
        assert updated.next_run_at is not None
        assert before + 2 * HOUR <= updated.next_run_at <= after + 2 * HOUR

    async def test_a_longer_cooldown_pushes_the_slot_past_it(self, stack: ManagerStack) -> None:
        job = await stack.create("cool", EVERY_HOUR)
        last_run = datetime.now(UTC) - timedelta(minutes=1)
        await stack.rewrite(job.id, last_run_at=last_run)

        updated = await stack.manager.update_job(job.id, CronJobPatch(cooldown_seconds=7200))

        assert updated is not None
        assert updated.next_run_at is not None
        assert updated.next_run_at >= last_run + 2 * HOUR

    async def test_an_active_window_moves_the_slot_into_it(self, stack: ManagerStack) -> None:
        window, opens = _window_ahead(6)
        job = await stack.create("windowed", EVERY_HOUR)

        before = datetime.now(UTC)
        updated = await stack.manager.update_job(job.id, CronJobPatch(active_hours=window))
        after = datetime.now(UTC)

        assert updated is not None
        assert updated.next_run_at is not None
        assert before + 6 * HOUR <= updated.next_run_at <= after + 6 * HOUR
        assert updated.next_run_at.hour == opens

    async def test_clearing_the_window_books_the_plain_next_slot(self, stack: ManagerStack) -> None:
        window, _ = _window_ahead(6)
        job = await stack.create("windowed", EVERY_HOUR, active_hours=window)

        before = datetime.now(UTC)
        updated = await stack.manager.update_job(job.id, CronJobPatch(clear_active_hours=True))
        after = datetime.now(UTC)

        assert updated is not None
        assert updated.next_run_at is not None
        assert before + HOUR <= updated.next_run_at <= after + HOUR

    async def test_a_due_one_shot_keeps_its_slot_when_only_the_window_or_the_cooldown_changes(
        self, stack: ManagerStack
    ) -> None:
        job = await stack.create("reminder", _once(HOUR))
        due = datetime.now(UTC) - timedelta(minutes=1)
        await stack.rewrite(job.id, schedule=_once(-HOUR), next_run_at=due)
        window, _ = _window_ahead(6)

        for edit in (
            CronJobPatch(cooldown_seconds=600),
            CronJobPatch(active_hours=window),
            CronJobPatch(clear_active_hours=True),
        ):
            updated = await stack.manager.update_job(job.id, edit)
            assert updated is not None
            assert updated.next_run_at == due

    async def test_an_unrelated_patch_keeps_the_booked_slot(self, stack: ManagerStack) -> None:
        job = await stack.create("hourly", EVERY_HOUR)
        updated = await stack.manager.update_job(job.id, CronJobPatch(name="renamed"))
        assert updated is not None
        assert updated.next_run_at == job.next_run_at

    async def test_a_paused_job_is_not_booked_by_a_schedule_edit(self, stack: ManagerStack) -> None:
        job = await stack.create("paused", EVERY_HOUR)
        await stack.rewrite(job.id, status=JobStatus.PAUSED, next_run_at=None)
        updated = await stack.manager.update_job(
            job.id, CronJobPatch(schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=7_200_000))
        )
        assert updated is not None
        assert updated.status == JobStatus.PAUSED
        assert updated.next_run_at is None


class TestToolReportsTheReason:
    async def _call(self, stack: ManagerStack, **args: object) -> str:
        tool = create_cron_tools(stack.manager, current_model="m", chat_id="c")[0]
        return str(await tool.ainvoke(args))

    async def test_add_in_the_past_returns_the_reason(self, stack: ManagerStack) -> None:
        past = (datetime.now(UTC) - HOUR).isoformat()
        assert await self._call(stack, action="add", prompt="call mom", at=past) == PASSED_ON_CREATE
        assert await stack.store.list_jobs() == []

    async def test_update_to_the_past_returns_the_reason(self, stack: ManagerStack) -> None:
        job = await stack.create("soon", _once(DAY))
        past = (datetime.now(UTC) - HOUR).isoformat()
        assert await self._call(stack, action="update", job_id=job.id, at=past) == PASSED_ON_CREATE

    async def test_resume_of_a_passed_one_shot_returns_the_reason(self, stack: ManagerStack) -> None:
        job = await stack.create("call-mom", _once(HOUR))
        await stack.manager.pause_job(job.id)
        await stack.rewrite(job.id, schedule=_once(-HOUR))
        assert await self._call(stack, action="resume", job_id=job.id) == PASSED_ON_RESUME
