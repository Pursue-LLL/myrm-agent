"""What a run leaves in ``last_error`` on a job that still carries an earlier failure.

A success clears ``last_error``, however the run was started. A failure replaces it with its own text wherever a run
closes (a scheduled run, a manual trial, a one-time job) and also when that failure pauses the job (a circuit break,
failures past ``max_retries``), because the failure alert of a paused job quotes it. A skipped run (a runner or probe
skip, a dispatch guard's refusal, a ``retry_at`` deferral, a slot found past its misfire grace) leaves it alone: the
failure the job already carries stays on it, on a one-time job as on a recurring one. Two related cases have their own
tests: a one-time job's success (``test_cron_once_completion.py``) and the reason written for a schedule that cannot
be computed (``test_cron_notices.py``). These scenarios run the real executor, or the startup recovery that skips a
late slot, over the in-memory store; only the runner, the delivery and the pre-flight probe are stand-ins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.engine.recovery import StartupRecovery
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.triggers import TriggerKind
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    PauseReason,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_EARLIER_FAILURE = "HTTP 500: upstream unavailable"
_LATEST_FAILURE = "HTTP 401: invalid credentials"
_EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)
_ONCE = Schedule(kind=ScheduleKind.ONCE, run_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
_MAX_RETRIES = 2

# A one-time job has a branch of its own in the shared skip record and in the startup recovery, so the cases that reach
# those run on both schedule shapes.
_ON_EITHER_SCHEDULE = pytest.mark.parametrize("schedule", [_EVERY_HOUR, _ONCE], ids=["recurring", "one_time"])


class _Runner:
    """Answers every run with the one result it was given."""

    def __init__(self, result: JobResult) -> None:
        self._result = result

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return self._result


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _ProbeFindsNothingToDo:
    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        return False, ""


async def _job_that_failed(
    *, probed: bool = False, schedule: Schedule = _EVERY_HOUR, failures: int = 0
) -> tuple[JobExecutor, InMemoryCronStore, CronJob]:
    store = InMemoryCronStore()
    job = CronJob(
        id="report",
        name="report",
        job_type=JobType.AGENT,
        schedule=schedule,
        prompt="send the report",
        delivery=DeliveryConfig(channel="chat"),
        pre_condition_script="check" if probed else None,
        max_retries=_MAX_RETRIES,
        consecutive_failures=failures,
        last_status=RunStatus.ERROR,
        last_error=_EARLIER_FAILURE,
    )
    await store.save_job(job)
    pre_condition = _ProbeFindsNothingToDo() if probed else None
    return JobExecutor(store=store, delivery=_Delivery(), pre_condition=pre_condition), store, job


async def _assert_failure_kept(store: InMemoryCronStore, job: CronJob) -> None:
    kept = await store.get_job(job.id)
    assert kept is not None
    assert kept.last_status == RunStatus.SKIPPED
    assert kept.last_error == _EARLIER_FAILURE


async def _assert_failure_kept_by_a_skipped_run(store: InMemoryCronStore, job: CronJob) -> None:
    await _assert_failure_kept(store, job)
    (run,) = await store.list_runs(job.id)
    assert run.status == RunStatus.SKIPPED


class TestASuccessClearsTheError:
    @pytest.mark.parametrize("trigger", [TriggerKind.CRON, TriggerKind.MANUAL], ids=["scheduled", "manual"])
    async def test_a_run_that_succeeds_leaves_no_error_on_the_job(self, trigger: TriggerKind) -> None:
        executor, store, job = await _job_that_failed()

        await executor.run_and_record(job, _Runner(JobResult(success=True, output="sent")), trigger_source=trigger)

        cleared = await store.get_job(job.id)
        assert cleared is not None
        assert cleared.last_status == RunStatus.OK
        assert cleared.last_error is None


class TestAFailureReplacesTheError:
    @pytest.mark.parametrize(
        ("schedule", "trigger"),
        [
            (_EVERY_HOUR, TriggerKind.CRON),
            (_EVERY_HOUR, TriggerKind.MANUAL),
            (_ONCE, TriggerKind.CRON),
        ],
        ids=["scheduled", "manual", "one_time"],
    )
    async def test_the_job_shows_the_latest_failure(self, schedule: Schedule, trigger: TriggerKind) -> None:
        executor, store, job = await _job_that_failed(schedule=schedule)
        failure = JobResult(success=False, error=_LATEST_FAILURE)

        await executor.run_and_record(job, _Runner(failure), trigger_source=trigger)

        replaced = await store.get_job(job.id)
        assert replaced is not None
        assert replaced.last_error == _LATEST_FAILURE

    @pytest.mark.parametrize(
        ("failures", "circuit_broken", "reason"),
        [
            (0, True, PauseReason.CIRCUIT_BREAK),
            (_MAX_RETRIES, False, PauseReason.RUN_FAILURES),
        ],
        ids=["circuit_break", "failures_past_the_limit"],
    )
    async def test_the_failure_that_pauses_the_job_is_the_one_it_shows(
        self, failures: int, circuit_broken: bool, reason: PauseReason
    ) -> None:
        executor, store, job = await _job_that_failed(failures=failures)
        failure = JobResult(success=False, error=_LATEST_FAILURE, circuit_broken=circuit_broken)

        await executor.run_and_record(job, _Runner(failure), trigger_source=TriggerKind.CRON)

        paused = await store.get_job(job.id)
        assert paused is not None
        assert (paused.status, paused.paused_reason) == (JobStatus.PAUSED, reason)
        assert paused.last_error == _LATEST_FAILURE


class TestASkippedRunKeepsTheError:
    async def test_a_dispatch_guard_refusal(self) -> None:
        executor, store, job = await _job_that_failed()

        await executor.record_guard_skip(job, reason="inside the cooldown", trigger_source=TriggerKind.CRON)

        await _assert_failure_kept_by_a_skipped_run(store, job)

    @_ON_EITHER_SCHEDULE
    async def test_a_runner_that_declares_a_skip(self, schedule: Schedule) -> None:
        executor, store, job = await _job_that_failed(schedule=schedule)
        skip = JobResult(success=True, skipped=True, skip_reason="nothing new")

        await executor.run_and_record(job, _Runner(skip))

        await _assert_failure_kept_by_a_skipped_run(store, job)

    async def test_a_probe_that_finds_nothing_to_do(self) -> None:
        executor, store, job = await _job_that_failed(probed=True)

        await executor.run_and_record(job, _Runner(JobResult(success=True, output="never runs")))

        await _assert_failure_kept_by_a_skipped_run(store, job)

    async def test_a_deferral_to_a_later_instant(self) -> None:
        executor, store, job = await _job_that_failed()
        retry_at = datetime.now(UTC) + timedelta(hours=2)
        deferral = JobResult(success=False, error="approval pending", retry_at=retry_at)

        await executor.run_and_record(job, _Runner(deferral))

        await _assert_failure_kept_by_a_skipped_run(store, job)

    @_ON_EITHER_SCHEDULE
    async def test_a_slot_found_past_its_misfire_grace(self, schedule: Schedule) -> None:
        _, store, job = await _job_that_failed(schedule=schedule)

        await StartupRecovery(store, AsyncMock()).reschedule_skipped(job.id)

        await _assert_failure_kept(store, job)
