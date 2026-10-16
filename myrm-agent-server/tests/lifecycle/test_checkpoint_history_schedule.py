"""The checkpoint-history prune is registered on the maintenance scheduler, delayed past startup."""

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

_JOB_ID = "checkpoint_history_prune"


class _RecordingScheduler:
    registered: dict[str, tuple[Callable[[], object], IntervalTrigger]] = {}
    ready = asyncio.Event()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        return None

    async def add_schedule(self, func: Callable[[], object], trigger: IntervalTrigger, *, id: str) -> None:  # noqa: A002
        type(self).registered[id] = (func, trigger)
        if id == _JOB_ID:
            type(self).ready.set()


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_RecordingScheduler]]:
    _RecordingScheduler.registered = {}
    _RecordingScheduler.ready = asyncio.Event()
    monkeypatch.setattr("apscheduler.AsyncScheduler", _RecordingScheduler)
    yield _RecordingScheduler
    task = schedulers._db_maintenance_scheduler_task
    if task is not None:
        task.cancel()
    monkeypatch.setattr(schedulers, "_db_maintenance_scheduler_task", None)
    monkeypatch.setattr(schedulers, "_db_maintenance_scheduler", None)


async def test_the_prune_runs_every_six_hours_starting_after_the_boot_burst(recording: type[_RecordingScheduler]) -> None:
    before = datetime.now(UTC)

    await schedulers.start_db_maintenance_scheduler()
    await asyncio.wait_for(recording.ready.wait(), timeout=10)

    func, trigger = recording.registered[_JOB_ID]
    assert func is schedulers._checkpoint_history_prune_job
    assert trigger.hours == 6
    assert before + timedelta(minutes=9) < trigger.start_time < before + timedelta(minutes=11)
    assert {"db_maintenance", "incognito_cleanup"} <= recording.registered.keys()  # the neighbours are untouched


async def test_the_job_delegates_to_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    prune = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.system.checkpoint_history_service.run_checkpoint_history_prune", prune)

    await schedulers._checkpoint_history_prune_job()

    prune.assert_awaited_once()
