"""The scheduled remote memory backup is registered on its own scheduler and drives the sync tick.

[INPUT]
app.lifecycle.schedulers::start_remote_backup_scheduler/_remote_backup_auto_sync_job
app.services.memory.backup.remote_sync::sync_tick

[OUTPUT]
That the hourly check is registered a few minutes after boot (not at once) and that the job feeds the stored settings,
the memory manager factory and the state store to the tick without ever raising.

[POS]
The real lifecycle functions with a recording ``AsyncScheduler``; the tick itself is covered in
``services/memory/backup/remote_sync/``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace, TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.lifecycle import schedulers
from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager
from app.services.memory.backup.remote_sync.state import RemoteSyncStore


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
    task = schedulers._remote_backup_scheduler_task
    if task is not None:
        task.cancel()
    monkeypatch.setattr(schedulers, "_remote_backup_scheduler_task", None)


async def test_the_hourly_check_is_registered_a_few_minutes_after_boot(recording: type[_RecordingScheduler]) -> None:
    before = datetime.now(UTC)

    await schedulers.start_remote_backup_scheduler()
    await asyncio.wait_for(recording.ready.wait(), timeout=10)

    [(job_id, func, trigger)] = recording.registered
    assert job_id == "remote_backup_auto_sync"
    assert func is schedulers._remote_backup_auto_sync_job
    assert trigger.minutes == 60
    # Not at once: an upload that is due from a closed period must not compete with startup.
    assert before + timedelta(minutes=4) < trigger.start_time < before + timedelta(minutes=6)
    assert recording.started


async def test_the_job_hands_the_stored_settings_to_the_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = {"enabled": True, "autoSync": True, "provider": "webdav"}
    monkeypatch.setattr("app.services.config.service.config_service.get", AsyncMock(return_value=SimpleNamespace(value=settings)))
    tick = AsyncMock()
    monkeypatch.setattr("app.services.memory.backup.remote_sync.sync_tick", tick)

    await schedulers._remote_backup_auto_sync_job()

    tick.assert_awaited_once()
    value = tick.await_args.args[0]
    options = tick.await_args.kwargs
    assert value == settings
    assert isinstance(options["store"], RemoteSyncStore)
    assert options["manager_factory"] is create_guardian_memory_manager
    assert isinstance(options["now"], datetime) and options["now"].tzinfo is not None


async def test_a_sync_that_was_never_configured_still_reaches_the_tick_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.config.service.config_service.get", AsyncMock(return_value=None))
    tick = AsyncMock()
    monkeypatch.setattr("app.services.memory.backup.remote_sync.sync_tick", tick)

    await schedulers._remote_backup_auto_sync_job()

    value: Mapping[str, object] | None = tick.await_args.args[0]
    assert value is None


async def test_a_failure_anywhere_in_the_job_never_escapes_to_the_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.config.service.config_service.get", AsyncMock(side_effect=RuntimeError("database locked")))

    await schedulers._remote_backup_auto_sync_job()
