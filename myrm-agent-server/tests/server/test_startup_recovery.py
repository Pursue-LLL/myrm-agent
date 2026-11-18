"""A failed database initialisation is repaired only when the file itself is damaged.

Salvage rewrites the file (the schema version resets, unreadable tables are lost, the isolated original is replaced by
the next attempt), so an intact file that failed for another reason must keep its bytes and surface the real error.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.platform_utils as platform_utils
from app.config.settings import settings
from app.database import connection
from app.database.operations import backup, recovery
from app.server.lifespan.startup_recovery import recover_failed_init
from app.server.status import system_status

_PAGE_SIZE = 4096


@dataclass
class _Scene:
    db_file: Path
    monkeypatch: pytest.MonkeyPatch
    init_database: AsyncMock
    reset_engine: AsyncMock
    rescue: MagicMock

    def damage(self) -> None:
        """Overwrite part of a data page, the way a torn write or a bad disk block would."""
        content = bytearray(self.db_file.read_bytes())
        content[_PAGE_SIZE * 2 + 100 : _PAGE_SIZE * 2 + 300] = b"\xff\x00\xde\xad" * 50
        self.db_file.write_bytes(content)
        assert recovery.database_is_damaged(str(self.db_file)), "the fixture must really damage the file"

    def restore_from(self, snapshot: str) -> None:
        manager = MagicMock()
        manager.restore_latest.return_value = SimpleNamespace(restored=True, snapshot_file=snapshot)
        self.monkeypatch.setattr(backup, "get_sqlite_backup_manager", lambda: manager)


@pytest.fixture
def scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Scene:
    db_file = tmp_path / "data.db"
    conn = sqlite3.connect(db_file)
    conn.execute(f"PRAGMA page_size = {_PAGE_SIZE}")
    conn.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany("INSERT INTO chats (title) VALUES (?)", [(f"chat {i}" * 20,) for i in range(300)])
    conn.commit()
    conn.close()

    init_database = AsyncMock()
    reset_engine = AsyncMock()
    rescue = MagicMock(return_value=False)
    monkeypatch.setattr(settings.database, "sqlite_path", str(db_file))
    monkeypatch.setattr(system_status, "database_recovered", False)
    monkeypatch.setattr(system_status, "database_degraded", False)
    monkeypatch.setattr(connection, "init_database", init_database)
    monkeypatch.setattr(platform_utils, "reset_database_engine", reset_engine)
    monkeypatch.setattr(recovery, "rescue_database", rescue)
    monkeypatch.setattr(backup, "get_sqlite_backup_manager", lambda: None)
    return _Scene(db_file, monkeypatch, init_database, reset_engine, rescue)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def test_an_intact_database_is_not_repaired_and_the_original_error_surfaces(scene: _Scene) -> None:
    before = _digest(scene.db_file)
    failure = RuntimeError("Database migration failed at version 7: boom")

    with pytest.raises(RuntimeError) as raised:
        await recover_failed_init(failure)

    assert raised.value is failure
    scene.rescue.assert_not_called()
    scene.init_database.assert_not_awaited()
    assert _digest(scene.db_file) == before
    assert not list(scene.db_file.parent.glob("*.corrupted"))
    assert (system_status.database_recovered, system_status.database_degraded) == (False, False)
    assert settings.database.sqlite_path == str(scene.db_file)


async def test_a_failure_carrying_a_corruption_report_is_repaired_although_the_probe_reads_clean(scene: _Scene) -> None:
    reported = sqlite3.DatabaseError("database disk image is malformed")
    reported.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    assert recovery.database_is_damaged(str(scene.db_file)) is False
    scene.rescue.return_value = True

    await recover_failed_init(reported)

    scene.rescue.assert_called_once_with(str(scene.db_file))
    scene.init_database.assert_awaited_once()
    assert (system_status.database_recovered, system_status.database_degraded) == (True, False)


async def test_a_damaged_database_is_salvaged_and_initialised_again(scene: _Scene) -> None:
    scene.damage()
    scene.rescue.return_value = True

    await recover_failed_init(RuntimeError("database disk image is malformed"))

    scene.rescue.assert_called_once_with(str(scene.db_file))
    scene.reset_engine.assert_awaited_once()
    scene.init_database.assert_awaited_once()
    assert (system_status.database_recovered, system_status.database_degraded) == (True, False)


async def test_a_salvaged_database_that_still_fails_to_initialise_ends_startup(scene: _Scene) -> None:
    scene.damage()
    scene.rescue.return_value = True
    scene.init_database.side_effect = RuntimeError("salvaged copy is unusable")

    with pytest.raises(RuntimeError, match="salvaged copy is unusable"):
        await recover_failed_init(RuntimeError("database disk image is malformed"))

    assert system_status.database_degraded is False


async def test_a_damaged_database_that_cannot_be_salvaged_is_restored_from_the_latest_snapshot(scene: _Scene) -> None:
    scene.damage()
    scene.restore_from("data-20261118.db")

    await recover_failed_init(RuntimeError("database disk image is malformed"))

    scene.init_database.assert_awaited_once()
    assert (system_status.database_recovered, system_status.database_degraded) == (True, False)
    assert settings.database.sqlite_path == str(scene.db_file)


async def test_a_restore_whose_initialisation_fails_degrades_to_memory(scene: _Scene) -> None:
    scene.damage()
    scene.restore_from("data-20261118.db")
    scene.init_database.side_effect = [RuntimeError("restored copy is unusable"), None]

    await recover_failed_init(RuntimeError("database disk image is malformed"))

    assert scene.init_database.await_count == 2
    assert settings.database.sqlite_path == ":memory:"
    assert (system_status.database_recovered, system_status.database_degraded) == (False, True)


async def test_with_nothing_to_restore_the_server_degrades_to_memory(scene: _Scene) -> None:
    scene.damage()

    await recover_failed_init(RuntimeError("database disk image is malformed"))

    scene.init_database.assert_awaited_once()
    assert settings.database.sqlite_path == ":memory:"
    assert (system_status.database_recovered, system_status.database_degraded) == (False, True)


async def test_a_missing_database_file_still_goes_through_the_restore_chain(scene: _Scene) -> None:
    scene.db_file.unlink()
    scene.restore_from("data-20261118.db")

    await recover_failed_init(RuntimeError("unable to open database file"))

    scene.rescue.assert_called_once_with(str(scene.db_file))
    scene.init_database.assert_awaited_once()
    assert (system_status.database_recovered, system_status.database_degraded) == (True, False)
