"""Unit tests for _build_daily_context in agent_runner.

Validates timezone handling, chronological ordering, cross-day summary,
and empty-history edge case.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

from app.core.cron.adapters.agent_runner import (
    _DAILY_CROSSDAY_SUMMARY_CHARS,
    _DAILY_MAX_HISTORY_ENTRIES,
    _DAILY_OUTPUT_TRUNCATE_CHARS,
    _build_daily_context,
)

_STORE_PATH = "app.core.cron.adapters.setup.get_cron_store"


def _make_daily_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "daily-1",
        "user_id": "user-1",
        "name": "test-daily",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Check status",
        "session_target": SessionTarget.DAILY,
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _make_run(
    *,
    finished_at: datetime,
    output: str | None = "ok",
    job_id: str = "daily-1",
) -> CronRunRecord:
    return CronRunRecord(
        id=f"run-{finished_at.isoformat()}",
        job_id=job_id,
        started_at=finished_at - timedelta(seconds=10),
        finished_at=finished_at,
        duration_ms=10_000,
        status=RunStatus.OK,
        output=output,
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_no_history_returns_empty() -> None:
    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert result == ""


@pytest.mark.asyncio
async def test_today_runs_in_chronological_order() -> None:
    """Fragments must appear oldest-first so the LLM sees natural time flow."""
    now = _now_utc()
    today_base = now.replace(hour=6, minute=0, second=0, microsecond=0)

    runs = [
        _make_run(finished_at=today_base.replace(hour=8), output="CPU 60%"),
        _make_run(finished_at=today_base.replace(hour=9), output="CPU 70%"),
        _make_run(finished_at=today_base.replace(hour=10), output="CPU 80%"),
    ]
    runs_desc = list(reversed(runs))

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=runs_desc)

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "08:00" in result
    assert "09:00" in result
    assert "10:00" in result
    idx_08 = result.index("08:00")
    idx_09 = result.index("09:00")
    idx_10 = result.index("10:00")
    assert idx_08 < idx_09 < idx_10, f"Expected chronological order, got: {result}"


@pytest.mark.asyncio
async def test_cross_day_injects_yesterday_summary() -> None:
    """First run of a new day should inject yesterday's last output."""
    now = _now_utc()
    yesterday = now - timedelta(days=1)
    yesterday_run = _make_run(
        finished_at=yesterday.replace(hour=22, minute=0),
        output="End of day summary: all systems normal",
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[yesterday_run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "Yesterday's last output" in result
    assert "End of day summary" in result


@pytest.mark.asyncio
async def test_output_truncation() -> None:
    """Output longer than _DAILY_OUTPUT_TRUNCATE_CHARS is truncated."""
    now = _now_utc()
    long_output = "x" * 1000
    run = _make_run(
        finished_at=now.replace(minute=0, second=0, microsecond=0),
        output=long_output,
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert len(result) < 1000
    assert "<daily_context>" in result


@pytest.mark.asyncio
async def test_naive_datetime_handled_gracefully() -> None:
    """_utc_date falls back to .date() for naive (tz-unaware) datetimes."""
    now = _now_utc()
    naive_dt = now.replace(tzinfo=None)
    run = _make_run(finished_at=now, output="aware result")
    naive_run = CronRunRecord(
        id="run-naive",
        job_id="daily-1",
        started_at=naive_dt - timedelta(seconds=10),
        finished_at=naive_dt,
        duration_ms=10_000,
        status=RunStatus.OK,
        output="naive result",
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[run, naive_run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "naive result" in result or "aware result" in result


@pytest.mark.asyncio
async def test_runs_with_none_output_returns_empty() -> None:
    """Runs whose output is None produce no fragments → empty string."""
    now = _now_utc()
    run = _make_run(
        finished_at=now.replace(minute=0, second=0, microsecond=0),
        output=None,
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert result == ""


@pytest.mark.asyncio
async def test_today_plus_yesterday_skips_yesterday_summary() -> None:
    """When today has runs, yesterday's summary must NOT be injected."""
    now = _now_utc()
    today_base = now.replace(hour=10, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)

    yesterday_run = _make_run(
        finished_at=yesterday.replace(hour=22, minute=0),
        output="Yesterday's final report",
    )
    today_run = _make_run(
        finished_at=today_base,
        output="Today's first check",
    )
    runs_desc = [today_run, yesterday_run]

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=runs_desc)

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "Today's first check" in result
    assert "Yesterday" not in result


@pytest.mark.asyncio
async def test_max_history_entries_cap() -> None:
    """Only the most recent _DAILY_MAX_HISTORY_ENTRIES runs are included."""
    now = _now_utc()
    today_base = now.replace(hour=1, minute=0, second=0, microsecond=0)

    runs = [
        _make_run(
            finished_at=today_base.replace(hour=i + 1),
            output=f"run-{i}",
        )
        for i in range(_DAILY_MAX_HISTORY_ENTRIES + 3)
    ]
    runs_desc = list(reversed(runs))

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=runs_desc)

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    included_count = result.count("[Previous run at")
    assert included_count == _DAILY_MAX_HISTORY_ENTRIES


@pytest.mark.asyncio
async def test_empty_string_output_produces_no_fragment() -> None:
    """Runs with output="" (empty string) should not produce fragments."""
    now = _now_utc()
    run = _make_run(
        finished_at=now.replace(minute=0, second=0, microsecond=0),
        output="",
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert result == ""


@pytest.mark.asyncio
async def test_crossday_summary_truncation() -> None:
    """Yesterday's summary is truncated to _DAILY_CROSSDAY_SUMMARY_CHARS."""
    now = _now_utc()
    yesterday = now - timedelta(days=1)
    long_output = "Y" * 1000
    yesterday_run = _make_run(
        finished_at=yesterday.replace(hour=23, minute=0),
        output=long_output,
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[yesterday_run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "Yesterday's last output" in result
    yesterday_marker = "[Yesterday's last output]\n"
    marker_idx = result.index(yesterday_marker)
    content_after_marker = result[marker_idx + len(yesterday_marker):]
    y_in_content = content_after_marker.count("Y")
    assert y_in_content <= _DAILY_CROSSDAY_SUMMARY_CHARS


@pytest.mark.asyncio
async def test_two_days_ago_not_injected() -> None:
    """Records from 2+ days ago should not appear in context."""
    now = _now_utc()
    two_days_ago = now - timedelta(days=2)
    old_run = _make_run(
        finished_at=two_days_ago.replace(hour=15, minute=0),
        output="Ancient history",
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[old_run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert result == ""


@pytest.mark.asyncio
async def test_output_exactly_at_truncation_boundary() -> None:
    """Output with exactly _DAILY_OUTPUT_TRUNCATE_CHARS is not truncated."""
    now = _now_utc()
    exact_output = "A" * _DAILY_OUTPUT_TRUNCATE_CHARS
    run = _make_run(
        finished_at=now.replace(minute=0, second=0, microsecond=0),
        output=exact_output,
    )

    job = _make_daily_job()
    mock_store = AsyncMock()
    mock_store.list_runs = AsyncMock(return_value=[run])

    with patch(_STORE_PATH, return_value=mock_store):
        result = await _build_daily_context(job)

    assert "A" * _DAILY_OUTPUT_TRUNCATE_CHARS in result
