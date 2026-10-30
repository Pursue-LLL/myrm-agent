"""A failed run that may already have had side effects is not repeated ahead of its schedule."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.engine.helpers import error_backoff_ms
from myrm_agent_harness.toolkits.cron.engine.parser import compute_next_run
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    DeliveryConfig,
    FailureAlertConfig,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_NOW = datetime(2026, 3, 1, 10, 30, tzinfo=UTC)
_ALERT_AFTER_THREE = CronConfig(failure_alert=FailureAlertConfig(enabled=True, after=3, cooldown_seconds=60))


def _job(**overrides: object) -> CronJob:
    schedule = overrides.pop("schedule", Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"))
    fields: dict[str, object] = {
        "id": "job-1",
        "user_id": "user-1",
        "name": "Morning digest",
        "job_type": JobType.AGENT,
        "schedule": schedule,
        "status": JobStatus.ACTIVE,
        "prompt": "send the digest",
        "delivery": DeliveryConfig(channel="chat"),
        "max_retries": 2,
    }
    fields.update(overrides)
    return CronJob(**fields)  # type: ignore[arg-type]


def _executor(config: CronConfig | None = None) -> tuple[JobExecutor, AsyncMock, AsyncMock]:
    store = AsyncMock()
    store.save_job = AsyncMock(side_effect=lambda j: j)
    store.save_run = AsyncMock()
    store.get_latest_integrity_hash = AsyncMock(return_value=None)
    delivery = AsyncMock()
    delivery.deliver = AsyncMock()
    return JobExecutor(store=store, delivery=delivery, config=config), store, delivery


def _store_holds(store: AsyncMock, job: CronJob) -> None:
    store.get_job = AsyncMock(side_effect=lambda job_id: job if job_id == job.id else None)


def _failed(*, retry_safe: bool, error: str = "provider returned an error") -> JobResult:
    return JobResult(success=False, error=error, retry_safe=retry_safe)


def test_job_result_is_retry_safe_by_default() -> None:
    assert JobResult(success=False, error="x").retry_safe is True


class TestRecurringJob:
    @pytest.mark.asyncio
    async def test_unsafe_failure_waits_for_the_next_regular_slot(self) -> None:
        executor, store, _ = _executor()
        job = _job()
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False), 1, _NOW)

        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at == compute_next_run(job.schedule, _NOW)
        assert job.next_run_at - _NOW > timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_safe_failure_still_retries_with_backoff(self) -> None:
        executor, store, _ = _executor()
        job = _job()
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=True), 1, _NOW)

        assert job.next_run_at == _NOW + timedelta(milliseconds=error_backoff_ms(1))

    @pytest.mark.asyncio
    async def test_unsafe_failure_is_still_counted_and_recorded(self) -> None:
        executor, store, _ = _executor()
        job = _job()
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False, error="boom"), 1, _NOW)

        assert job.consecutive_failures == 1
        assert job.last_status == RunStatus.ERROR
        assert job.last_error == "boom"

    @pytest.mark.asyncio
    async def test_unsafe_failures_still_pause_the_job_past_max_retries(self) -> None:
        executor, store, _ = _executor()
        job = _job(max_retries=2)
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False), 3, _NOW)

        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None

    @pytest.mark.asyncio
    async def test_timeout_leaves_the_job_for_its_next_regular_slot(self) -> None:
        executor, store, _ = _executor()
        job = _job()
        _store_holds(store, job)
        runner = AsyncMock()
        runner.run = AsyncMock(side_effect=TimeoutError)

        await executor.run_and_record(job, runner)

        assert job.consecutive_failures == 1
        assert job.last_run_at is not None
        assert job.next_run_at == compute_next_run(job.schedule, job.last_run_at)
        assert "timed out" in (job.last_error or "")


class TestOneShotJob:
    @pytest.mark.asyncio
    async def test_transient_failure_of_a_safe_run_is_retried(self) -> None:
        executor, store, _ = _executor()
        job = _job(schedule=Schedule(kind=ScheduleKind.ONCE, run_at=_NOW), max_retries=3)
        _store_holds(store, job)

        await executor._handle_once_completion(job, _failed(retry_safe=True, error="rate limit exceeded"), 1, _NOW)

        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at == _NOW + timedelta(milliseconds=error_backoff_ms(1))

    @pytest.mark.asyncio
    async def test_transient_failure_of_an_unsafe_run_is_not_retried(self) -> None:
        executor, store, _ = _executor()
        job = _job(schedule=Schedule(kind=ScheduleKind.ONCE, run_at=_NOW), max_retries=3)
        _store_holds(store, job)

        await executor._handle_once_completion(job, _failed(retry_safe=False, error="rate limit exceeded"), 1, _NOW)

        assert job.status == JobStatus.PAUSED
        assert job.next_run_at is None


class TestFailureAlert:
    @staticmethod
    async def _alert_text(delivery: AsyncMock) -> str:
        await asyncio.sleep(0)
        delivery.deliver.assert_awaited_once()
        alert: JobResult = delivery.deliver.call_args.args[1]
        return alert.output

    @pytest.mark.asyncio
    async def test_unsafe_failure_alerts_without_waiting_for_the_threshold(self) -> None:
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job()
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False), 1, _NOW)

        text = await self._alert_text(delivery)
        assert "not re-run ahead of schedule" in text
        assert job.next_run_at is not None
        assert job.next_run_at.isoformat() in text
        assert job.last_failure_alert_at == _NOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("retry_safe", "max_retries"),
        [(False, 5), (True, 5), (False, 2)],
        ids=["not-repeatable", "backoff-retry", "paused"],
    )
    async def test_alert_text_is_plain_and_names_no_product_screen(self, retry_safe: bool, max_retries: int) -> None:
        """The alert reaches the person who owns the task: no framework jargon, no path through someone's UI."""
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job(max_retries=max_retries)
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=retry_safe), 3, _NOW)

        text = await self._alert_text(delivery)
        assert text == text.strip()
        assert "Settings" not in text
        assert "side effects" not in text

    @pytest.mark.asyncio
    async def test_safe_failure_below_the_threshold_stays_quiet(self) -> None:
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job()
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=True), 1, _NOW)
        await asyncio.sleep(0)

        delivery.deliver.assert_not_awaited()
        assert job.last_failure_alert_at is None

    @pytest.mark.asyncio
    async def test_cooldown_still_throttles_unsafe_failures(self) -> None:
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job(last_failure_alert_at=_NOW - timedelta(seconds=10))
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False), 1, _NOW)
        await asyncio.sleep(0)

        delivery.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_safe_failure_alert_promises_a_backoff_retry(self) -> None:
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job(max_retries=5)
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=True), 3, _NOW)

        assert "will retry with backoff" in await self._alert_text(delivery)

    @pytest.mark.asyncio
    async def test_alert_of_a_paused_job_says_so(self) -> None:
        executor, store, delivery = _executor(_ALERT_AFTER_THREE)
        job = _job(max_retries=2)
        _store_holds(store, job)

        await executor._update_after_run(job, _failed(retry_safe=False), 3, _NOW)

        text = await self._alert_text(delivery)
        assert "auto-paused" in text
        assert "not re-run" not in text
