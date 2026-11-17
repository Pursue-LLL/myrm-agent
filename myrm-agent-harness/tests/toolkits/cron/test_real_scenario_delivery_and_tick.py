"""Real-scenario tests for delivery edge cases and scheduler ticks over an InMemoryCronStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_scenario_fakes import FakeAgentRunner, FakeDelivery

# ---------------------------------------------------------------------------
# Scenario 4: Delivery edge cases
# ---------------------------------------------------------------------------


class TestDeliveryEdgeCases:
    @pytest.fixture
    def store(self) -> InMemoryCronStore:
        return InMemoryCronStore()

    @pytest.fixture
    def delivery(self) -> FakeDelivery:
        return FakeDelivery()

    @pytest.fixture
    def executor(self, store: InMemoryCronStore, delivery: FakeDelivery) -> JobExecutor:
        return JobExecutor(store=store, delivery=delivery)

    @pytest.fixture
    def scheduler_mock(self) -> MagicMock:
        s = MagicMock()
        s.notify_change = MagicMock()
        return s

    @pytest.fixture
    def manager(self, store: InMemoryCronStore, scheduler_mock: MagicMock) -> CronManager:
        return CronManager(store=store, scheduler=scheduler_mock, shell_enabled=True)

    @pytest.mark.asyncio
    async def test_silent_response_skips_delivery(
        self,
        manager: CronManager,
        executor: JobExecutor,
        delivery: FakeDelivery,
    ) -> None:
        job = await manager.create_job(
            name="Silent Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="check something quietly",
        )

        silent_runner = FakeAgentRunner(output="[SILENT]")
        await executor.run_and_record(job, silent_runner)

        assert len(delivery.deliveries) == 0

    @pytest.mark.asyncio
    async def test_none_channel_skips_delivery(
        self,
        manager: CronManager,
        executor: JobExecutor,
        delivery: FakeDelivery,
    ) -> None:
        job = await manager.create_job(
            name="No Delivery",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="internal task",
            delivery=DeliveryConfig(channel="none"),
        )

        runner = FakeAgentRunner(output="done")
        await executor.run_and_record(job, runner)

        assert len(delivery.deliveries) == 0

    @pytest.mark.asyncio
    async def test_dedup_skips_duplicate(
        self,
        manager: CronManager,
        executor: JobExecutor,
        delivery: FakeDelivery,
    ) -> None:
        job = await manager.create_job(
            name="Dedup Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="check status",
            deduplicate=True,
        )

        runner = FakeAgentRunner(output="status: OK")
        await executor.run_and_record(job, runner)
        assert len(delivery.deliveries) == 1

        await executor.run_and_record(job, runner)
        assert len(delivery.deliveries) == 1


# ---------------------------------------------------------------------------
# Scenario 5: Scheduler _on_tick integration
# ---------------------------------------------------------------------------


class TestSchedulerOnTick:
    """Test scheduler's _on_tick dispatching with real store."""

    @pytest.mark.asyncio
    async def test_on_tick_dispatches_due_jobs(self) -> None:
        store = InMemoryCronStore()
        delivery = FakeDelivery()
        agent_runner = FakeAgentRunner()

        scheduler = CronScheduler(
            store=store,
            runners={JobType.AGENT: agent_runner},
            delivery=delivery,
            config=CronConfig(max_concurrent=3),
        )

        now = datetime.now(UTC)
        job = CronJob(
            id="tick-job-1",
            name="Due Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="* * * * *"),
            status=JobStatus.ACTIVE,
            prompt="run me",
            next_run_at=now - timedelta(seconds=5),
            delivery=DeliveryConfig(channel="chat"),
        )
        await store.save_job(job)

        scheduler._running = True
        await scheduler._on_tick()

        # Poll until the dispatched task reports back. The ceiling is generous on purpose:
        # the dispatch is a fire-and-forget task, and under a full-suite run the event
        # loop can be busy enough that a 2 s window flakes even though nothing is wrong.
        deadline = asyncio.get_running_loop().time() + 10.0
        while agent_runner.call_count < 1 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)

        await scheduler.stop()

        assert agent_runner.call_count == 1
        runs = await store.list_runs("tick-job-1")
        assert len(runs) == 1
        assert runs[0].status == RunStatus.OK

    @pytest.mark.asyncio
    async def test_on_tick_skips_past_grace(self) -> None:
        store = InMemoryCronStore()
        delivery = FakeDelivery()
        agent_runner = FakeAgentRunner()

        scheduler = CronScheduler(
            store=store,
            runners={JobType.AGENT: agent_runner},
            delivery=delivery,
        )

        now = datetime.now(UTC)
        job = CronJob(
            id="stale-job",
            name="Stale Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            status=JobStatus.ACTIVE,
            prompt="run me",
            next_run_at=now - timedelta(seconds=600),
            misfire_grace_seconds=60,
            delivery=DeliveryConfig(channel="chat"),
        )
        await store.save_job(job)

        scheduler._running = True
        await scheduler._on_tick()
        await asyncio.sleep(0.2)

        assert agent_runner.call_count == 0
