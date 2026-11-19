"""What a run leaves in ``last_error`` on a job that still carries an earlier failure.

A success clears ``last_error``, however the run was started, and a skipped run (a runner or probe skip, a dispatch
guard's refusal, a ``retry_at`` deferral, a slot found past its misfire grace) leaves it alone: the failure the job
already carries stays on it. Two related cases have their own tests: a one-time job's success
(``test_cron_once_completion.py``) and the reason written for a schedule that cannot be computed
(``test_cron_notices.py``). These scenarios run the real executor, or the startup recovery that skips a late slot, over
the in-memory store; only the runner, the delivery and the pre-flight probe are stand-ins.
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
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_EARLIER_FAILURE = "HTTP 500: upstream unavailable"
_EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)


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


async def _job_that_failed(*, probed: bool = False) -> tuple[JobExecutor, InMemoryCronStore, CronJob]:
    store = InMemoryCronStore()
    job = CronJob(
        id="report",
        name="report",
        job_type=JobType.AGENT,
        schedule=_EVERY_HOUR,
        prompt="send the report",
        delivery=DeliveryConfig(channel="chat"),
        pre_condition_script="check" if probed else None,
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


class TestASkippedRunKeepsTheError:
    async def test_a_dispatch_guard_refusal(self) -> None:
        executor, store, job = await _job_that_failed()

        await executor.record_guard_skip(job, reason="inside the cooldown", trigger_source=TriggerKind.CRON)

        await _assert_failure_kept_by_a_skipped_run(store, job)

    async def test_a_runner_that_declares_a_skip(self) -> None:
        executor, store, job = await _job_that_failed()
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

    async def test_a_slot_found_past_its_misfire_grace(self) -> None:
        _, store, job = await _job_that_failed()

        await StartupRecovery(store, AsyncMock()).reschedule_skipped(job.id)

        await _assert_failure_kept(store, job)
