"""Real-scenario tests for the job lifecycle: full runs, failure handling and CRUD.

Uses InMemoryCronStore as a real store (no mocks) to validate
the full lifecycle: create → schedule → execute → deliver → state update.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from tests.support.cron_scenario_fakes import FakeAgentRunner, FakeDelivery, FakeShellRunner

# ---------------------------------------------------------------------------
# Scenario 1: Full lifecycle — create, execute, verify state
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Create a job via CronManager, execute it via JobExecutor, verify state."""

    @pytest.fixture
    def store(self) -> InMemoryCronStore:
        return InMemoryCronStore()

    @pytest.fixture
    def delivery(self) -> FakeDelivery:
        return FakeDelivery()

    @pytest.fixture
    def agent_runner(self) -> FakeAgentRunner:
        return FakeAgentRunner()

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
    async def test_agent_job_full_lifecycle(
        self,
        manager: CronManager,
        executor: JobExecutor,
        agent_runner: FakeAgentRunner,
        store: InMemoryCronStore,
        delivery: FakeDelivery,
    ) -> None:
        job = await manager.create_job(
            name="Daily Report",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
            prompt="Generate daily report",
            model="gpt-4",
        )
        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at is not None

        persisted = await store.get_job(job.id)
        assert persisted is not None
        assert persisted.name == "Daily Report"

        await executor.run_and_record(job, agent_runner)

        assert agent_runner.call_count == 1
        assert len(delivery.deliveries) == 1
        _delivered_job, delivered_result = delivery.deliveries[0]
        assert delivered_result.success is True
        assert "Agent completed task" in delivered_result.output

        runs = await store.list_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.OK
        assert runs[0].job_id == job.id

        updated_job = await store.get_job(job.id)
        assert updated_job is not None
        assert updated_job.last_status == RunStatus.OK
        assert updated_job.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_shell_job_lifecycle(
        self,
        manager: CronManager,
        executor: JobExecutor,
        store: InMemoryCronStore,
        delivery: FakeDelivery,
    ) -> None:
        shell_runner = FakeShellRunner(output="disk usage: 42%")

        job = await manager.create_job(
            name="Disk Check",
            job_type=JobType.SHELL,
            schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3600000),
            command="df -h",
        )

        await executor.run_and_record(job, shell_runner)

        assert shell_runner.call_count == 1
        runs = await store.list_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.OK
        assert "disk usage" in (runs[0].output or "")

    @pytest.mark.asyncio
    async def test_once_job_auto_delete(
        self,
        manager: CronManager,
        executor: JobExecutor,
        agent_runner: FakeAgentRunner,
        store: InMemoryCronStore,
    ) -> None:
        run_at = datetime.now(UTC) + timedelta(minutes=5)
        job = await manager.create_job(
            name="One-time Task",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.ONCE, run_at=run_at),
            prompt="Do this once",
        )
        assert job.delete_after_run is True

        await executor.run_and_record(job, agent_runner)

        deleted_job = await store.get_job(job.id)
        assert deleted_job is None


# ---------------------------------------------------------------------------
# Scenario 2: Failure handling and auto-pause
# ---------------------------------------------------------------------------


class TestFailureHandling:
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
    async def test_consecutive_failures_auto_pause(
        self,
        manager: CronManager,
        executor: JobExecutor,
        store: InMemoryCronStore,
    ) -> None:
        """After max_retries+1 consecutive failures, job should auto-pause."""
        failing_runner = FakeAgentRunner(success=False)

        job = await manager.create_job(
            name="Flaky Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="*/5 * * * *"),
            prompt="do something",
            max_retries=2,
        )

        for _i in range(3):
            await executor.run_and_record(job, failing_runner)

        updated = await store.get_job(job.id)
        assert updated is not None
        assert updated.status == JobStatus.PAUSED
        assert updated.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_success_resets_failures(
        self,
        manager: CronManager,
        executor: JobExecutor,
        store: InMemoryCronStore,
    ) -> None:
        job = await manager.create_job(
            name="Recovery Job",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="do something",
            max_retries=5,
        )

        failing_runner = FakeAgentRunner(success=False)
        await executor.run_and_record(job, failing_runner)
        await executor.run_and_record(job, failing_runner)

        mid = await store.get_job(job.id)
        assert mid is not None
        assert mid.consecutive_failures == 2

        success_runner = FakeAgentRunner(success=True)
        await executor.run_and_record(job, success_runner)

        recovered = await store.get_job(job.id)
        assert recovered is not None
        assert recovered.consecutive_failures == 0
        assert recovered.last_status == RunStatus.OK


# ---------------------------------------------------------------------------
# Scenario 3: CRUD operations via CronManager
# ---------------------------------------------------------------------------


class TestCRUDOperations:
    @pytest.fixture
    def store(self) -> InMemoryCronStore:
        return InMemoryCronStore()

    @pytest.fixture
    def scheduler_mock(self) -> MagicMock:
        s = MagicMock()
        s.notify_change = MagicMock()
        return s

    @pytest.fixture
    def manager(self, store: InMemoryCronStore, scheduler_mock: MagicMock) -> CronManager:
        return CronManager(store=store, scheduler=scheduler_mock, shell_enabled=True)

    @pytest.mark.asyncio
    async def test_create_list_get_delete(self, manager: CronManager) -> None:
        job = await manager.create_job(
            name="Test CRUD",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="test",
        )

        jobs = await manager.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == job.id

        fetched = await manager.get_job(job.id)
        assert fetched is not None
        assert fetched.name == "Test CRUD"

        assert await manager.delete_job(job.id) is True
        assert await manager.get_job(job.id) is None

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, manager: CronManager) -> None:
        job = await manager.create_job(
            name="Pausable",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
            prompt="test",
        )

        paused = await manager.pause_job(job.id)
        assert paused is not None
        assert paused.status == JobStatus.PAUSED

        resumed = await manager.resume_job(job.id)
        assert resumed is not None
        assert resumed.status == JobStatus.ACTIVE
        assert resumed.next_run_at is not None

    @pytest.mark.asyncio
    async def test_trigger_now(self, manager: CronManager) -> None:
        job = await manager.create_job(
            name="Triggerable",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 0 1 1 *"),
            prompt="test",
        )

        triggered = await manager.trigger_now(job.id)
        assert triggered is True
