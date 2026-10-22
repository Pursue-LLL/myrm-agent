"""The scheduled instance backup is actually registered on the maintenance scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.lifecycle import schedulers


class _RecordingScheduler:
    registered: list[tuple[str, Callable[[], object], IntervalTrigger]] = []
    ready = asyncio.Event()
    started = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        return None

    async def add_schedule(self, func: Callable[[], object], trigger: IntervalTrigger, *, id: str) -> None:  # noqa: A002
        type(self).registered.append((id, func, trigger))
        if id == "instance_auto_backup":
            type(self).ready.set()

    async def start_in_background(self) -> None:
        type(self).started = True


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_RecordingScheduler]]:
    _RecordingScheduler.registered = []
    _RecordingScheduler.ready = asyncio.Event()
    _RecordingScheduler.started = False
    monkeypatch.setattr("apscheduler.AsyncScheduler", _RecordingScheduler)
    yield _RecordingScheduler
    task = schedulers._db_maintenance_scheduler_task
    if task is not None:
        task.cancel()
    monkeypatch.setattr(schedulers, "_db_maintenance_scheduler_task", None)
    monkeypatch.setattr(schedulers, "_db_maintenance_scheduler", None)


async def test_the_hourly_backup_check_is_registered_a_few_minutes_after_boot(recording: type[_RecordingScheduler]) -> None:
    before = datetime.now(UTC)

    await schedulers.start_db_maintenance_scheduler()
    await asyncio.wait_for(recording.ready.wait(), timeout=10)

    by_id = {job_id: (func, trigger) for job_id, func, trigger in recording.registered}
    func, trigger = by_id["instance_auto_backup"]
    assert func is schedulers._instance_auto_backup_job
    assert trigger.minutes == 60
    assert before + timedelta(minutes=4) < trigger.start_time < before + timedelta(minutes=6)
    assert {"db_maintenance", "incognito_cleanup"} <= by_id.keys()  # the neighbours are untouched
    # APScheduler only runs schedules after an explicit start; registering alone leaves them dead.
    assert recording.started


async def test_the_job_delegates_to_the_service_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    tick = AsyncMock()
    monkeypatch.setattr("app.services.instance_archive.auto_backup.run_auto_backup_tick", tick)

    await schedulers._instance_auto_backup_job()

    tick.assert_awaited_once()
