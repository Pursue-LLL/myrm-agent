"""The scheduled remote memory backup is registered on its own scheduler and drives the sync tick.

[INPUT]
app.lifecycle.schedulers::start_remote_backup_scheduler/_remote_backup_auto_sync_job
app.services.memory.backup.remote_sync::sync_tick

[OUTPUT]
That the hourly check is registered a few minutes after boot (not at once), that the job feeds the stored settings,
the memory manager factory and the state store to the tick without ever raising, and that settings sealed by a key that
is gone reach the tick as unreadable.

[POS]
The real lifecycle functions with a recording ``AsyncScheduler``; the tick itself is covered in
``services/memory/backup/remote_sync/``. The unreadable-settings case reads a real sealed row through the real
``ConfigService`` on an in-memory database.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace, TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import UserConfig
from app.lifecycle import schedulers
from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager
from app.services.config import service as config_service_module
from app.services.config.encryption import ConfigEncryptionService
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
    record = SimpleNamespace(value=settings, unreadable=False)
    monkeypatch.setattr("app.services.config.service.config_service.get", AsyncMock(return_value=record))
    tick = AsyncMock()
    monkeypatch.setattr("app.services.memory.backup.remote_sync.sync_tick", tick)

    await schedulers._remote_backup_auto_sync_job()

    tick.assert_awaited_once()
    value = tick.await_args.args[0]
    options = tick.await_args.kwargs
    assert value == settings
    assert options["settings_unreadable"] is False
    assert isinstance(options["store"], RemoteSyncStore)
    assert options["manager_factory"] is create_guardian_memory_manager
    assert isinstance(options["now"], datetime) and options["now"].tzinfo is not None


@pytest.mark.parametrize(
    ("record", "unreadable"),
    [
        (SimpleNamespace(value={}, unreadable=True), True),  # sealed, but the key that sealed it no longer opens it
        (SimpleNamespace(value={}, unreadable=False), False),  # an empty row that was never secret, or sealed and saved empty
        (SimpleNamespace(value={"enabled": False}, unreadable=False), False),
        (None, False),
    ],
    ids=["undecryptable", "empty-but-readable", "readable", "never-saved"],
)
async def test_stored_settings_that_cannot_be_decrypted_are_told_apart_from_settings_that_were_never_saved(
    monkeypatch: pytest.MonkeyPatch, record: SimpleNamespace | None, unreadable: bool
) -> None:
    monkeypatch.setattr("app.services.config.service.config_service.get", AsyncMock(return_value=record))
    tick = AsyncMock()
    monkeypatch.setattr("app.services.memory.backup.remote_sync.sync_tick", tick)

    await schedulers._remote_backup_auto_sync_job()

    assert tick.await_args.kwargs["settings_unreadable"] is unreadable


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


@pytest.fixture
async def stored_rows(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(config_service_module, "get_session_factory", lambda: sessions)
    yield sessions
    await engine.dispose()


async def test_settings_sealed_by_a_key_that_is_gone_reach_the_tick_as_unreadable(
    stored_rows: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    lost = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    current = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    sealed, encrypted = lost.encrypt_if_needed("backupSync", {"enabled": True, "autoSync": True, "provider": "webdav"})
    assert encrypted
    async with stored_rows() as db:
        db.add(
            UserConfig(
                id="id-backupSync",
                config_key="backupSync",
                config_value=sealed,
                is_encrypted=True,
                version="1_0",
                last_device_id="device",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
    monkeypatch.setattr(config_service_module, "get_encryption_service", lambda: current)
    tick = AsyncMock()
    monkeypatch.setattr("app.services.memory.backup.remote_sync.sync_tick", tick)

    await schedulers._remote_backup_auto_sync_job()

    tick.assert_awaited_once()
    assert tick.await_args.args[0] == {}
    assert tick.await_args.kwargs["settings_unreadable"] is True
