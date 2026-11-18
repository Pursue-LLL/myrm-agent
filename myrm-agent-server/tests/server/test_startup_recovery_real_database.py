"""The startup recovery chain against a real database: real schema, real migrations, real salvage.

``test_startup_recovery.py`` pins each branch with stand-ins; these two runs show what a user's file goes through. A page
of the migration state table, which every start reads, is damaged: the file is salvaged with its rows (including those
of a table whose name ends like an FTS4 shadow table) and the next start finishes without replaying the migrations. A
migration that fails on a healthy file leaves it byte for byte as it was.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from app.config.settings import settings
from app.database import migrations
from app.database.connection import init_database
from app.database.operations.recovery import database_is_damaged
from app.platform_utils import get_database_engine, reset_database_engine
from app.server.lifespan.startup_recovery import recover_failed_init
from app.server.status import system_status

pytestmark = pytest.mark.integration

_STATE_TABLE = "_schema_migrations"
_RECALL_TEXT = "the quarterly budget review"


@pytest.fixture
async def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A healthy database file, initialised the way the first start does it, with no connection left open on it."""
    db_file = tmp_path / "data.db"
    monkeypatch.setattr(settings.database, "sqlite_path", str(db_file))
    monkeypatch.setattr(system_status, "database_recovered", False)
    monkeypatch.setattr(system_status, "database_degraded", False)
    await reset_database_engine()
    await init_database()
    await reset_database_engine()
    yield db_file
    await reset_database_engine()


def _damage_root_page(db_file: Path, table: str) -> None:
    """Write junk over the start of a table's root page, where its B-tree header and first rows live."""
    with sqlite3.connect(db_file) as conn:
        (root_page,) = conn.execute("SELECT rootpage FROM sqlite_master WHERE name = ?", (table,)).fetchone()
        (page_size,) = conn.execute("PRAGMA page_size").fetchone()
    with db_file.open("r+b") as handle:
        handle.seek((root_page - 1) * page_size)
        handle.write(b"\xff\x00\xde\xad" * 25)


def _seed_recall_segment(db_file: Path) -> None:
    """A row in ``conversation_recall_segments``: its name ends like an FTS4 shadow table, yet it holds real rows."""
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO conversation_recall_segments (chat_id, message_id, role, segment_text) "
            "VALUES ('chat-1', 'message-1', 'user', ?)",
            (_RECALL_TEXT,),
        )


def _recall_segment_texts(db_file: Path) -> list[str]:
    with sqlite3.connect(db_file) as conn:
        return [text for (text,) in conn.execute("SELECT segment_text FROM conversation_recall_segments")]


async def test_a_database_with_a_damaged_state_table_page_is_salvaged_with_its_rows_and_starts_again(
    database: Path,
) -> None:
    _seed_recall_segment(database)
    _damage_root_page(database, _STATE_TABLE)
    assert database_is_damaged(str(database))

    with pytest.raises(Exception, match="malformed|corrupt") as failed:
        await init_database()
    await recover_failed_init(failed.value)

    assert system_status.database_recovered is True
    assert not database_is_damaged(str(database))
    assert (database.parent / "data.db.corrupted").exists()
    assert await migrations.has_pending_migrations(get_database_engine()) is False
    assert _recall_segment_texts(database) == [_RECALL_TEXT]


async def test_a_failing_migration_on_a_healthy_database_surfaces_and_leaves_the_file_alone(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_later = [*migrations.MIGRATION_STATEMENTS, "ALTER TABLE no_such_table ADD COLUMN extra TEXT"]
    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", shipped_later)
    with pytest.raises(RuntimeError, match="no such table: no_such_table") as failed:
        await init_database()
    await reset_database_engine()
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError) as surfaced:
        await recover_failed_init(failed.value)

    assert surfaced.value is failed.value
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not list(database.parent.glob("*.corrupted"))
    assert (system_status.database_recovered, system_status.database_degraded) == (False, False)
