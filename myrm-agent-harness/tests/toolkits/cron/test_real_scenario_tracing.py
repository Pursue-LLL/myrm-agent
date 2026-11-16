"""Real-scenario tests that the tracing context reaches the runner through a real store, executor and scheduler."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.observability.tracing import TracingContext
from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_scenario_fakes import FakeDelivery

# ---------------------------------------------------------------------------
# Scenario 6: TracingContext propagation through full execution pipeline
# ---------------------------------------------------------------------------


class TracingCaptureRunner:
    """Runner that captures TracingContext state during execution."""

    def __init__(self) -> None:
        self.captured_trace_ids: list[str] = []
        self.captured_session_ids: list[str] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.captured_trace_ids.append(TracingContext.get_trace_id())
        self.captured_session_ids.append(TracingContext.get_session_id())
        return JobResult(success=True, output="traced output")


class TestTracingContextPropagation:
    """Verify trace_id/session_id propagate through real Scheduler→Executor→Runner chain."""

    @pytest.fixture
    def store(self) -> InMemoryCronStore:
        return InMemoryCronStore()

    @pytest.fixture
    def delivery(self) -> FakeDelivery:
        return FakeDelivery()

    @pytest.fixture
    def tracing_runner(self) -> TracingCaptureRunner:
        return TracingCaptureRunner()

    @pytest.mark.asyncio
    async def test_executor_injects_trace_id_in_real_store(
        self,
        store: InMemoryCronStore,
        delivery: FakeDelivery,
        tracing_runner: TracingCaptureRunner,
    ) -> None:
        """Full lifecycle: Executor with InMemoryCronStore, no mocks on tracing."""
        executor = JobExecutor(store=store, delivery=delivery)
        job = CronJob(
            id="traced-job-1",
            name="Traced Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="trace me",
            delivery=DeliveryConfig(channel="chat"),
        )
        await store.save_job(job)

        await executor.run_and_record(job, tracing_runner)

        assert len(tracing_runner.captured_trace_ids) == 1
        tid = tracing_runner.captured_trace_ids[0]
        assert tid != "-"
        assert len(tid) == 32
        int(tid, 16)

        assert tracing_runner.captured_session_ids[0] == "traced-job-1"

        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"

    @pytest.mark.asyncio
    async def test_scheduler_on_tick_propagates_tracing(
        self,
        store: InMemoryCronStore,
        delivery: FakeDelivery,
        tracing_runner: TracingCaptureRunner,
    ) -> None:
        """Scheduler._on_tick dispatch through Executor→Runner carries trace_id."""
        now = datetime.now(UTC)
        job = CronJob(
            id="tick-traced",
            name="Tick Traced Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", stagger_ms=0),
            status=JobStatus.ACTIVE,
            prompt="tick prompt",
            delivery=DeliveryConfig(channel="chat"),
            next_run_at=now - timedelta(seconds=5),
        )
        await store.save_job(job)

        scheduler = CronScheduler(
            store=store,
            runners={JobType.AGENT: tracing_runner},
            delivery=delivery,
        )
        scheduler._running = True
        await scheduler._on_tick()

        await asyncio.sleep(0.3)

        assert len(tracing_runner.captured_trace_ids) == 1
        tid = tracing_runner.captured_trace_ids[0]
        assert tid != "-"
        assert len(tid) == 32
        assert tracing_runner.captured_session_ids[0] == "tick-traced"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_jobs_get_distinct_trace_ids(
        self,
        store: InMemoryCronStore,
        delivery: FakeDelivery,
    ) -> None:
        """Parallel job executions each get their own trace_id (no cross-contamination)."""
        captured: list[tuple[str, str]] = []

        class SlowCapturingRunner:
            async def run(self, job: CronJob, *, context: str = "") -> JobResult:
                tid = TracingContext.get_trace_id()
                sid = TracingContext.get_session_id()
                await asyncio.sleep(0.05)
                # After sleep, context should still be the same
                assert TracingContext.get_trace_id() == tid
                assert TracingContext.get_session_id() == sid
                captured.append((tid, sid))
                return JobResult(success=True, output=f"done-{job.id}")

        executor = JobExecutor(store=store, delivery=delivery)
        runner = SlowCapturingRunner()

        jobs = []
        for i in range(3):
            job = CronJob(
                id=f"parallel-{i}",
                name=f"Parallel Job {i}",
                job_type=JobType.AGENT,
                schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
                prompt=f"run {i}",
                delivery=DeliveryConfig(channel="chat"),
            )
            await store.save_job(job)
            jobs.append(job)

        await asyncio.gather(*(executor.run_and_record(job, runner) for job in jobs))

        assert len(captured) == 3
        trace_ids = [t[0] for t in captured]
        session_ids = [t[1] for t in captured]

        # All trace_ids are unique
        assert len(set(trace_ids)) == 3
        # Each session_id matches its job.id
        assert set(session_ids) == {"parallel-0", "parallel-1", "parallel-2"}
        # Context is reset after all complete
        assert TracingContext.get_trace_id() == "-"
        assert TracingContext.get_session_id() == "-"
