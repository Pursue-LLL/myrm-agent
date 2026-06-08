"""Unit tests for app.core.infra.health.sqlite — SQLiteHealthChecker."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.infra.health.health_checker import HealthStatus, RecoveryStatus


def _create_test_db(db_path: Path, *, rows: int = 10) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, data TEXT)")
    for i in range(rows):
        conn.execute("INSERT INTO items (data) VALUES (?)", (f"row-{i}",))
    conn.commit()
    conn.close()


def _corrupt_db(db_path: Path) -> None:
    data = bytearray(db_path.read_bytes())
    page_size = 4096
    for page_idx in range(1, min(4, len(data) // page_size)):
        start = page_idx * page_size
        end = min(start + page_size, len(data))
        for i in range(start, end):
            data[i] = 0x00
    db_path.write_bytes(bytes(data))


@pytest.mark.asyncio
async def test_check_healthy_db(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_test_db(db)

    with patch("app.core.infra.health.sqlite.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY
        assert "quick_check passed" in result.message


@pytest.mark.asyncio
async def test_check_nonexistent_db(tmp_path: Path) -> None:
    db = tmp_path / "nonexistent.db"

    with patch("app.core.infra.health.sqlite.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY
        assert "does not exist yet" in result.message


@pytest.mark.asyncio
async def test_check_corrupted_db(tmp_path: Path) -> None:
    db = tmp_path / "corrupt.db"
    _create_test_db(db, rows=100)
    _corrupt_db(db)

    with patch("app.core.infra.health.sqlite.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_check_not_a_database(tmp_path: Path) -> None:
    db = tmp_path / "garbage.db"
    db.write_bytes(b"not a sqlite database" * 100)

    with patch("app.core.infra.health.sqlite.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_recover_from_backup(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_test_db(db, rows=50)

    backup_dir = db.parent / "sqlite_backups"
    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    mgr = SQLiteBackupManager(db, backup_dir)
    mgr.create_backup()

    _corrupt_db(db)

    with (
        patch("app.core.infra.health.sqlite.settings") as mock_settings,
        patch("app.core.infra.health.sqlite.get_sqlite_backup_manager", return_value=mgr),
    ):
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.recover()

        assert result.status == RecoveryStatus.SUCCESS
        assert "restored" in result.message.lower()

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    assert count == 50


@pytest.mark.asyncio
async def test_recover_no_backups(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_test_db(db)

    with (
        patch("app.core.infra.health.sqlite.settings") as mock_settings,
        patch("app.core.infra.health.sqlite.get_sqlite_backup_manager", return_value=None),
    ):
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker()
        result = await checker.recover()

        assert result.status == RecoveryStatus.FAILED


@pytest.mark.asyncio
async def test_force_wal_cleanup_ignored(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_test_db(db)

    with patch("app.core.infra.health.sqlite.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.core.infra.health.sqlite import SQLiteHealthChecker

        checker = SQLiteHealthChecker(force_wal_cleanup=True)
        result = await checker.check()
        assert result.status == HealthStatus.HEALTHY
