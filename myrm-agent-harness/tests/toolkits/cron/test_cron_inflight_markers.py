"""A run in flight leaves a marker, and a start reports what the previous process left behind instead of losing it.

The scheduler writes a persisted marker for every run before anything else and clears it when the job's last run
ends. A start turns the markers the previous process left into interrupted-run records, one counted failure each,
before it replays what came due; what the application hears of them is in ``test_cron_interrupted_notice.py``.
Every test drives the real scheduler, executor and recovery over the in-memory store; only the runner, the lock and
the injected store faults are stand-ins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine import scheduler_dispatch
from myrm_agent_harness.toolkits.cron.engine.recovery import StartupRecovery
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryStatus,
    JobStatus,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_inflight_stack import (
    CRASHED,
    ONCE,
    PATIENCE_S,
    STOPPING,
    EventLock,
    InflightStack,
    SlowClearStore,
    make_inflight_stack,
)


@pytest.fixture
def stack() -> InflightStack:
    return make_inflight_stack()


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the test acts: the scheduler's own timers must never fire."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, 3600.0)


class TestMarkerLifecycle:
    async def test_a_run_is_marked_while_it_is_in_flight_and_unmarked_when_it_ends(self, stack: InflightStack) -> None:
        job = await stack.add()
        before = datetime.now(UTC)
        await stack.launch(job)

        [(job_id, started)] = await stack.store.list_running()
        assert job_id == job.id and before <= started <= datetime.now(UTC)

        stack.runner.gate.set()
        await stack.drain()
        assert await stack.markers() == []

    async def test_the_marker_is_written_before_the_stagger_wait(
        self, stack: InflightStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scheduler_dispatch, "random", SimpleNamespace(randint=lambda _low, high: high))
        job = await stack.add(schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=60_000))
        stack.scheduler._launch(job)
        await stack.settle()

        assert stack.runner.runs == 0, "the run is still waiting out its stagger delay"
        assert await stack.markers() == [job.id]
        await stack.end_runs()

    async def test_overlapping_runs_of_one_job_share_a_marker_that_the_last_one_clears(
        self, stack: InflightStack
    ) -> None:
        job = await stack.add()
        await stack.launch(job, trigger_source="event")
        await stack.launch(job, trigger_source="event")
        assert await stack.markers() == [job.id]

        first = next(iter(stack.scheduler._bg_tasks))
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        assert await stack.markers() == [job.id], "one run is still in flight"

        stack.runner.gate.set()
        await stack.drain()
        assert await stack.markers() == []

    async def test_a_cancelled_run_keeps_its_marker_and_leaves_nothing_counted_in_flight(
        self, stack: InflightStack
    ) -> None:
        job = await stack.add()
        await stack.launch(job)
        await stack.end_runs()

        assert await stack.markers() == [job.id]
        assert not stack.scheduler._in_flight

    async def test_a_marker_that_cannot_be_written_costs_the_report_not_the_run(
        self, stack: InflightStack, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(stack.store, "mark_running", AsyncMock(side_effect=OSError("disk full")))
        job = await stack.add()
        with caplog.at_level(logging.WARNING):
            await stack.launch(job)
            stack.runner.gate.set()
            await stack.drain()

        assert stack.runner.runs == 1 and (await stack.stored()).last_status == RunStatus.OK
        assert "could not write its in-flight marker" in caplog.text

    async def test_a_marker_that_cannot_be_cleared_is_a_warning_and_the_run_still_closes(
        self, stack: InflightStack, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(stack.store, "clear_running", AsyncMock(side_effect=OSError("disk full")))
        job = await stack.add()
        with caplog.at_level(logging.WARNING):
            await stack.launch(job)
            stack.runner.gate.set()
            await stack.drain()

        assert (await stack.stored()).last_status == RunStatus.OK
        assert "could not clear its in-flight marker" in caplog.text

    async def test_a_finished_run_clears_its_marker_even_when_cancelled_while_clearing(self) -> None:
        store = SlowClearStore()
        stack = make_inflight_stack(store)
        job = await stack.add()
        stack.runner.gate.set()
        stack.scheduler._launch(job)
        await asyncio.wait_for(store.clearing.wait(), timeout=PATIENCE_S)

        for task in list(stack.scheduler._bg_tasks):
            task.cancel()
        store.clear_gate.set()
        await stack.drain()
        await stack.settle()

        assert await stack.markers() == []


class TestReportInterrupted:
    @staticmethod
    def _recovery(stack: InflightStack) -> StartupRecovery:
        return StartupRecovery(stack.store, AsyncMock())

    async def test_a_start_records_a_crashed_run_and_counts_one_failure(self, stack: InflightStack) -> None:
        job = await stack.add()
        await stack.store.mark_running(job.id)
        [(_, started)] = await stack.store.list_running()

        await self._recovery(stack).report_interrupted(counted=True)

        [run] = await stack.store.list_runs(job.id)
        assert (run.status, run.trigger_source, run.error) == (RunStatus.ERROR, "recovery", CRASHED)
        assert (run.delivery_status, run.started_at, run.duration_ms) == (DeliveryStatus.SKIPPED, started, 0)
        stored = await stack.stored()
        assert (stored.last_status, stored.last_error, stored.consecutive_failures) == (RunStatus.ERROR, CRASHED, 1)
        assert stored.status == JobStatus.ACTIVE and stored.next_run_at == job.next_run_at
        assert await stack.markers() == []

    async def test_a_job_over_its_failure_budget_is_paused_and_one_at_the_budget_is_not(
        self, stack: InflightStack
    ) -> None:
        at_budget = await stack.add("at-budget", consecutive_failures=1, max_retries=2)
        over_budget = await stack.add("over-budget", consecutive_failures=2, max_retries=2)
        for job in (at_budget, over_budget):
            await stack.store.mark_running(job.id)

        await self._recovery(stack).report_interrupted(counted=True)

        at, over = await stack.stored("at-budget"), await stack.stored("over-budget")
        assert (at.status, at.consecutive_failures) == (JobStatus.ACTIVE, 2) and at.next_run_at is not None
        assert (over.status, over.consecutive_failures, over.next_run_at) == (JobStatus.PAUSED, 3, None)

    async def test_a_graceful_stop_records_the_run_and_counts_nothing(self, stack: InflightStack) -> None:
        job = await stack.add(consecutive_failures=2, max_retries=2)
        await stack.store.mark_running(job.id)
        [(_, started)] = await stack.store.list_running()

        await self._recovery(stack).report_interrupted(counted=False)

        [run] = await stack.store.list_runs(job.id)
        assert (run.status, run.trigger_source, run.error) == (RunStatus.ERROR, "shutdown", STOPPING)
        assert (run.started_at, run.delivery_status) == (started, DeliveryStatus.SKIPPED) and run.finished_at >= started
        stored = await stack.stored()
        assert (stored.status, stored.last_status, stored.consecutive_failures, stored.last_error) == (
            JobStatus.ACTIVE,
            RunStatus.ERROR,
            2,
            STOPPING,
        )
        assert stored.next_run_at is not None and await stack.markers() == []

    async def test_the_marker_of_a_deleted_job_is_dropped_without_a_record(self, stack: InflightStack) -> None:
        await stack.store.mark_running("gone")

        await self._recovery(stack).report_interrupted(counted=True)

        assert await stack.markers() == [] and await stack.store.list_runs() == []

    async def test_a_job_that_cannot_be_recorded_does_not_hold_back_the_others(
        self, stack: InflightStack, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        for job_id in ("a", "b"):
            await stack.add(job_id)
            await stack.store.mark_running(job_id)
        get_job = stack.store.get_job

        async def failing_for_a(job_id: str) -> CronJob | None:
            if job_id == "a":
                raise OSError("unreadable row")
            return await get_job(job_id)

        monkeypatch.setattr(stack.store, "get_job", failing_for_a)
        with caplog.at_level(logging.WARNING):
            await self._recovery(stack).report_interrupted(counted=True)

        assert await stack.interrupted("b") == [("recovery", CRASHED)]
        assert await stack.markers() == [] and "Job a: could not record its interrupted run" in caplog.text


class TestStart:
    async def test_an_interrupted_one_shot_within_its_grace_is_delivered_again(self, stack: InflightStack) -> None:
        job = await stack.add(schedule=ONCE)
        await stack.store.mark_running(job.id)
        stack.runner.gate.set()

        await stack.scheduler.start()
        await stack.drain()

        assert stack.runner.runs == 1 and (await stack.stored()).status == JobStatus.COMPLETED
        assert sorted(str(source) for source, _ in await stack.interrupted()) == ["cron", "recovery"]
        await stack.scheduler.stop()

    async def test_an_interrupted_one_shot_past_its_grace_is_completed_not_run(self, stack: InflightStack) -> None:
        job = await stack.add(schedule=ONCE, due=timedelta(hours=1))
        await stack.store.mark_running(job.id)

        await stack.scheduler.start()
        await stack.drain()

        stored = await stack.stored()
        assert stack.runner.runs == 0 and (stored.status, stored.last_status) == (
            JobStatus.COMPLETED,
            RunStatus.SKIPPED,
        )
        assert stored.consecutive_failures == 1 and await stack.interrupted() == [("recovery", CRASHED)]
        await stack.scheduler.stop()

    async def test_an_interrupted_one_shot_over_its_failure_budget_is_paused_not_run(
        self, stack: InflightStack
    ) -> None:
        job = await stack.add(schedule=ONCE, consecutive_failures=2, max_retries=2)
        await stack.store.mark_running(job.id)

        await stack.scheduler.start()
        await stack.drain()

        stored = await stack.stored()
        assert stack.runner.runs == 0 and (stored.status, stored.next_run_at) == (JobStatus.PAUSED, None)
        await stack.scheduler.stop()

    async def test_the_report_comes_before_the_catch_up(self, stack: InflightStack) -> None:
        job = await stack.add(schedule=ONCE)
        await stack.store.mark_running(job.id)
        failures_when_admitted: list[int] = []

        async def admit(due: CronJob) -> None:
            failures_when_admitted.append((await stack.stored(due.id)).consecutive_failures)

        await StartupRecovery(stack.store, admit).run()

        assert failures_when_admitted == [1]

    async def test_a_scheduler_that_stands_by_leaves_the_markers_to_the_lock_holder(self) -> None:
        stack = make_inflight_stack(lock=EventLock([], free=False))
        job = await stack.add()
        await stack.store.mark_running(job.id)

        await stack.scheduler.start()

        assert await stack.markers() == [job.id] and await stack.store.list_runs() == []
        assert not stack.scheduler.health()["running"]
