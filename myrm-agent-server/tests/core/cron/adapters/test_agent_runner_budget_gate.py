"""A cron run the budget blocks is skipped, not failed: the budget reopens while the job stays as it is."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters import agent_runner
from app.core.cron.adapters.agent_runner import AgentJobRunner

_BUDGET_GATE = "app.services.budget.enforcer.should_block_execution"
_CAPABILITIES = "app.platform_utils.deployment_capabilities.get_deployment_capabilities"


def _schedule(kind: ScheduleKind) -> Schedule:
    if kind is ScheduleKind.ONCE:
        return Schedule(kind=kind, run_at=datetime.now(UTC) + timedelta(minutes=5))
    if kind is ScheduleKind.CRON:
        return Schedule(kind=kind, expr="0 9 * * *")
    return Schedule(kind=kind, interval_ms=300_000)


def _job(kind: ScheduleKind = ScheduleKind.INTERVAL, **overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "job-1",
        "user_id": "default",
        "name": "Inbox triage",
        "job_type": JobType.AGENT,
        "schedule": _schedule(kind),
        "status": JobStatus.ACTIVE,
        "prompt": "Triage the inbox.",
        "delivery": DeliveryConfig(channel="chat"),
        "max_retries": 2,
    }
    fields.update(overrides)
    return CronJob(**fields)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_memory_pressure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_runner, "_memory_overload_reason", lambda: None)


@pytest.fixture(autouse=True)
def _local_deployment() -> Iterator[None]:
    with patch(_CAPABILITIES, return_value=SimpleNamespace(uses_platform_budget=False)):
        yield


@pytest.fixture
def budget_blocked() -> Iterator[AsyncMock]:
    with patch(_BUDGET_GATE, new_callable=AsyncMock, return_value=True) as gate:
        yield gate


@pytest.mark.usefixtures("budget_blocked")
class TestBudgetBlockedRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", [ScheduleKind.CRON, ScheduleKind.INTERVAL])
    async def test_a_recurring_run_is_skipped(self, kind: ScheduleKind) -> None:
        result = await AgentJobRunner()._run_once(_job(kind))

        assert (result.success, result.skipped, result.skip_reason, result.retry_at) == (False, True, "budget_blocked", None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("hosted", "code"), [(False, "budget_blocked"), (True, "credit_exhausted")], ids=["local", "hosted"])
    async def test_the_skip_code_names_what_ran_out(self, hosted: bool, code: str) -> None:
        with patch(_CAPABILITIES, return_value=SimpleNamespace(uses_platform_budget=hosted)):
            result = await AgentJobRunner()._run_once(_job())

        assert result.skip_reason == code

    @pytest.mark.asyncio
    async def test_a_one_shot_run_fails_because_a_skip_would_consume_it(self) -> None:
        result = await AgentJobRunner()._run_once(_job(ScheduleKind.ONCE))

        assert (result.success, result.skipped, result.retry_safe) == (False, False, False)
        assert "budget" in (result.error or "")

    @pytest.mark.asyncio
    async def test_the_skip_is_logged_as_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger=agent_runner.logger.name):
            await AgentJobRunner()._run_once(_job())

        assert [r.levelno for r in caplog.records if "job-1" in r.getMessage() and "budget" in r.getMessage()] == [
            logging.WARNING
        ]


@pytest.mark.asyncio
async def test_the_retry_loop_asks_the_budget_once_and_does_not_wait(
    budget_blocked: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(agent_runner.asyncio, "sleep", sleep)

    result = await AgentJobRunner()._run_with_retries(_job(max_retries=2), context="")

    assert result.skipped is True
    assert budget_blocked.await_count == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_job_blocked_slot_after_slot_stays_active_without_failures(budget_blocked: AsyncMock) -> None:
    """End to end: the executor records each blocked slot as skipped, so no failure ever adds up to an auto-pause."""
    job = _job(max_retries=2)
    store = AsyncMock()
    store.get_latest_integrity_hash = AsyncMock(return_value=None)
    store.get_job = AsyncMock(return_value=job)
    executor = JobExecutor(store=store, delivery=AsyncMock())

    for _ in range(5):
        await executor.run_and_record(job, AgentJobRunner())

    assert budget_blocked.await_count == 5
    assert [call.args[0].status for call in store.save_run.call_args_list] == [RunStatus.SKIPPED] * 5
    assert (job.status, job.consecutive_failures) == (JobStatus.ACTIVE, 0)
    assert job.next_run_at is not None
