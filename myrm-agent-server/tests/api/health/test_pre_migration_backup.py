"""Tests for pre-migration safety snapshot in init_database().

Verifies that backup_database() is called before run_migrations()
to protect multi-step DDL migrations from partial failure.
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.recovery import backup_database, restore_from_backup


@pytest.mark.asyncio
async def test_init_database_calls_backup_before_migrations():
    """backup_database() must execute before run_migrations()."""
    call_order: list[str] = []

    def fake_backup(path: str) -> None:
        call_order.append("backup")

    async def fake_run_migrations(engine: object) -> None:
        call_order.append("migrations")

    async def fake_create_indexes(engine: object) -> None:
        call_order.append("indexes")

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.recovery.backup_database", side_effect=fake_backup),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.database.sqlite_path = "/tmp/test.db"

        from app.database.connection import init_database

        await init_database()

    assert "backup" in call_order, "backup_database was not called"
    assert "migrations" in call_order, "run_migrations was not called"
    backup_idx = call_order.index("backup")
    migrations_idx = call_order.index("migrations")
    assert backup_idx < migrations_idx, (
        f"backup must run before migrations, got order: {call_order}"
    )


@pytest.mark.asyncio
async def test_init_database_continues_when_backup_fails():
    """If backup_database() raises, init_database() must still proceed."""
    migrations_ran = False

    async def fake_run_migrations(engine: object) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    async def fake_create_indexes(engine: object) -> None:
        pass

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.recovery.backup_database", side_effect=OSError("disk full")),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.database.sqlite_path = "/tmp/test.db"

        from app.database.connection import init_database

        await init_database()

    assert migrations_ran, "run_migrations must execute even when backup fails"


# --- Edge-case tests (no mocks, real sqlite3) ---


def test_backup_skips_nonexistent_db(tmp_path: Path):
    """backup_database() silently returns when the DB file does not exist."""
    missing = str(tmp_path / "nonexistent.db")
    backup_database(missing)
    assert not (tmp_path / "nonexistent.db.bak").exists()


def test_backup_overwrites_existing_bak(tmp_path: Path):
    """A second backup overwrites the previous .db.bak file."""
    db = tmp_path / "overwrite.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('v1')")
    conn.commit()
    conn.close()

    backup_database(str(db))

    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO t VALUES ('v2')")
    conn.commit()
    conn.close()

    backup_database(str(db))

    bak = sqlite3.connect(str(db.with_suffix(".db.bak")))
    rows = bak.execute("SELECT v FROM t ORDER BY v").fetchall()
    bak.close()
    assert [r[0] for r in rows] == ["v1", "v2"]


def test_backup_then_restore_after_simulated_migration_failure(tmp_path: Path):
    """Simulates: backup → destructive migration fails midway → restore recovers data."""
    db = tmp_path / "migrate_fail.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cron_jobs (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO cron_jobs VALUES (1, 'daily_report')")
    conn.execute("INSERT INTO cron_jobs VALUES (2, 'weekly_sync')")
    conn.commit()
    conn.close()

    backup_database(str(db))

    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cron_jobs_new AS SELECT id, name FROM cron_jobs")
    conn.execute("DROP TABLE cron_jobs")
    conn.close()

    assert restore_from_backup(str(db)) is True

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT count(*) FROM cron_jobs").fetchone()[0]
    conn.close()
    assert count == 2
