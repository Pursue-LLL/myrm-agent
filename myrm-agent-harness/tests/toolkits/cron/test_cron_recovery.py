"""Unit tests for StartupRecovery: a replay of missed cron slots, then a catch-up of the jobs that came due.

Every enabled job keeps a next run time through a restart, so recovery only decides what happens to the slots that came
due while the process was down: it hands a job to the scheduler's admission, which books the next slot and launches the
run, or, for a job past its misfire grace, books the next slot itself and skips the late one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from myrm_agent_harness.toolkits.cron.engine.recovery import StartupRecovery
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)
_SCHED_CRON = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *")
_SCHED_ONCE = Schedule(kind=ScheduleKind.ONCE, run_at=_NOW + timedelta(hours=1))
_DELIVERY = DeliveryConfig(channel="none")


def _job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "j1",
        "name": "test",
        "job_type": JobType.SHELL,
        "command": "echo hi",
        "schedule": _SCHED_CRON,
        "delivery": _DELIVERY,
        "status": JobStatus.ACTIVE,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


def _recovery(*jobs: CronJob) -> tuple[StartupRecovery, AsyncMock, AsyncMock]:
    """A recovery over a store that lists ``jobs`` and finds each by id; returns it with its store and admission."""
    store, admit = AsyncMock(), AsyncMock()
    store.list_jobs = AsyncMock(return_value=list(jobs))
    store.get_job = AsyncMock(side_effect=lambda job_id: next((job for job in jobs if job.id == job_id), None))
    return StartupRecovery(store=store, admit_fn=admit), store, admit


class TestReplayMissedSlots:
    async def test_replays_missed(self) -> None:
        job = _job(last_run_at=_NOW - timedelta(hours=3))
        recovery, _, admit = _recovery(job)

        await recovery._replay_missed_slots()

        admit.assert_awaited_once_with(job)

    async def test_skips_paused(self) -> None:
        recovery, _, admit = _recovery(_job(status=JobStatus.PAUSED, last_run_at=_NOW - timedelta(hours=3)))

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()

    async def test_skips_interval(self) -> None:
        job = _job(
            schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000), last_run_at=_NOW - timedelta(hours=3)
        )
        recovery, _, admit = _recovery(job)

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()

    async def test_skips_no_last_run(self) -> None:
        recovery, _, admit = _recovery(_job(last_run_at=None))

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()

    async def test_no_jobs(self) -> None:
        recovery, _, admit = _recovery()

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()

    async def test_skips_error_backoff(self) -> None:
        """Job in error backoff should not be replayed."""
        job = _job(
            last_run_at=datetime.now(UTC) - timedelta(seconds=10),
            last_status=RunStatus.ERROR,
            consecutive_failures=3,
            retry_backoff_ms=3_600_000,
        )
        recovery, _, admit = _recovery(job)

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()

    async def test_skips_a_slot_that_elapsed_before_the_last_edit(self) -> None:
        """A slot before the last edit or resume was never owed to anyone."""
        recovery, _, admit = _recovery(_job(last_run_at=_NOW - timedelta(hours=3), updated_at=datetime.now(UTC)))

        await recovery._replay_missed_slots()

        admit.assert_not_awaited()


class TestExecuteDueWithinGrace:
    async def test_executes_due_jobs(self) -> None:
        due_job = _job(next_run_at=datetime.now(UTC) - timedelta(seconds=30), misfire_grace_seconds=300)
        recovery, _, admit = _recovery(due_job)

        await recovery._execute_due_within_grace()

        admit.assert_awaited_once_with(due_job)

    async def test_books_the_next_slot_of_a_job_past_grace_and_runs_nothing(self) -> None:
        past_grace = _job(next_run_at=datetime.now(UTC) - timedelta(hours=2), misfire_grace_seconds=60)
        recovery, store, admit = _recovery(past_grace)

        await recovery._execute_due_within_grace()

        admit.assert_not_awaited()
        store.save_job.assert_awaited_once()
        saved = store.save_job.call_args[0][0]
        assert saved.next_run_at is not None and saved.next_run_at > datetime.now(UTC)
        assert saved.last_status == RunStatus.SKIPPED

    async def test_leaves_a_job_in_error_backoff_for_the_tick(self) -> None:
        now = datetime.now(UTC)
        in_backoff = _job(
            next_run_at=now - timedelta(seconds=30),
            last_run_at=now - timedelta(seconds=10),
            last_status=RunStatus.ERROR,
            consecutive_failures=3,
            retry_backoff_ms=3_600_000,
        )
        recovery, store, admit = _recovery(in_backoff)

        await recovery._execute_due_within_grace()

        admit.assert_not_awaited()
        store.save_job.assert_not_awaited()

    async def test_no_due_jobs(self) -> None:
        recovery, store, admit = _recovery()

        await recovery._execute_due_within_grace()

        admit.assert_not_awaited()
        store.save_job.assert_not_awaited()


class TestRescheduleSkipped:
    async def test_reschedule_cron(self) -> None:
        recovery, store, _ = _recovery(_job(next_run_at=_NOW - timedelta(hours=1)))

        await recovery.reschedule_skipped("j1")

        store.save_job.assert_awaited_once()
        saved = store.save_job.call_args[0][0]
        assert saved.next_run_at is not None and saved.next_run_at > datetime.now(UTC)
        assert saved.last_status == RunStatus.SKIPPED

    async def test_reschedule_once_completes(self) -> None:
        recovery, store, _ = _recovery(_job(schedule=_SCHED_ONCE))

        await recovery.reschedule_skipped("j1")

        saved = store.save_job.call_args[0][0]
        assert saved.status == JobStatus.COMPLETED
        assert saved.next_run_at is None

    async def test_reschedule_not_found(self) -> None:
        recovery, store, _ = _recovery()

        await recovery.reschedule_skipped("j1")

        store.save_job.assert_not_awaited()

    async def test_a_paused_job_is_left_alone(self) -> None:
        recovery, store, _ = _recovery(_job(status=JobStatus.PAUSED))

        await recovery.reschedule_skipped("j1")

        store.save_job.assert_not_awaited()


class TestRun:
    async def test_run_goes_through_both_phases(self) -> None:
        recovery, store, _ = _recovery()

        await recovery.run()

        assert store.list_jobs.call_count == 2
