"""Provider usage-limit deferral for cron agent runs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, MyrmLLMError

from app.core.cron.adapters.agent_runner import AgentJobRunner, _failure_result
from app.core.cron.adapters.provider_window_deferral import USAGE_LIMIT_SKIP_REASON, usage_limit_deferral

_NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)


def _limit_error(cooldown_ms: int | None) -> MyrmLLMError:
    context = {"cooldown_remaining_ms": cooldown_ms} if cooldown_ms is not None else None
    return MyrmLLMError(error_code=FailoverReason.RATE_LIMIT, default_msg="usage limit reached", context=context)


def _schedule(kind: ScheduleKind) -> Schedule:
    if kind is ScheduleKind.ONCE:
        return Schedule(kind=kind, run_at=_NOW + timedelta(minutes=5))
    if kind is ScheduleKind.CRON:
        return Schedule(kind=kind, expr="0 * * * *")
    return Schedule(kind=kind, interval_ms=3_600_000)


def _job(kind: ScheduleKind = ScheduleKind.INTERVAL, **overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-1",
        "user_id": "default",
        "name": "report",
        "job_type": JobType.AGENT,
        "schedule": _schedule(kind),
        "prompt": "report",
        "max_retries": 3,
        "retry_backoff_ms": 100,
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


def test_deferral_targets_the_provider_boundary() -> None:
    result = usage_limit_deferral(_limit_error(3 * 3600 * 1000), now=_NOW)

    assert result is not None
    assert result.success is False
    assert result.skip_reason == USAGE_LIMIT_SKIP_REASON
    assert result.retry_at == _NOW + timedelta(hours=3)


@pytest.mark.parametrize("cooldown_ms", [None, 0, 25 * 3600 * 1000])
def test_no_deferral_without_a_waitable_boundary(cooldown_ms: int | None) -> None:
    assert usage_limit_deferral(_limit_error(cooldown_ms), now=_NOW) is None


def test_foreign_errors_keep_the_failure_path() -> None:
    result = _failure_result(_job(), RuntimeError("boom"))

    assert result.success is False
    assert result.retry_at is None
    assert result.error == "boom"


def test_failure_result_defers_a_usage_limit() -> None:
    result = _failure_result(_job(), _limit_error(60_000))

    assert result.retry_at is not None
    assert result.skip_reason == USAGE_LIMIT_SKIP_REASON


@pytest.mark.asyncio
async def test_run_does_not_retry_in_process_against_a_closed_window(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = AgentJobRunner()
    deferral = usage_limit_deferral(_limit_error(3600 * 1000), now=_NOW)
    run_once = AsyncMock(return_value=deferral)
    monkeypatch.setattr(runner, "_run_once", run_once)

    result = await runner.run(_job(max_retries=3))

    assert result is deferral
    assert run_once.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expects_retry"),
    [(ScheduleKind.ONCE, True), (ScheduleKind.INTERVAL, False), (ScheduleKind.CRON, False)],
)
async def test_memory_overload_only_rearms_one_shot_jobs(
    monkeypatch: pytest.MonkeyPatch, kind: ScheduleKind, expects_retry: bool
) -> None:
    monkeypatch.setattr("app.core.cron.adapters.agent_runner._memory_overload_reason", lambda: "memory_pressure:high")
    result = await AgentJobRunner().run(_job(kind))

    assert result.skipped is True
    assert (result.retry_at is not None) is expects_retry


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [ScheduleKind.INTERVAL, ScheduleKind.ONCE])
async def test_executor_parks_the_job_until_the_reset_instead_of_failing_it(
    monkeypatch: pytest.MonkeyPatch, kind: ScheduleKind
) -> None:
    """End to end: a usage-limit failure re-arms the job and counts no failure."""
    runner = AgentJobRunner()
    job = _job(kind, consecutive_failures=2, max_retries=2)

    async def _hits_limit(_job: CronJob, *, context: str = "") -> JobResult:
        return _failure_result(_job, _limit_error(2 * 3600 * 1000))

    monkeypatch.setattr(runner, "_run_once", _hits_limit)
    store = AsyncMock()
    store.get_latest_integrity_hash = AsyncMock(return_value=None)
    store.get_job = AsyncMock(return_value=job)
    delivery = AsyncMock()
    before = datetime.now(UTC)

    await JobExecutor(store=store, delivery=delivery).run_and_record(job, runner)

    assert store.save_run.call_args[0][0].status is RunStatus.SKIPPED
    assert job.status is JobStatus.ACTIVE
    assert job.consecutive_failures == 2
    assert job.next_run_at is not None
    assert before + timedelta(hours=2) <= job.next_run_at <= datetime.now(UTC) + timedelta(hours=2)
    delivery.deliver.assert_not_awaited()
