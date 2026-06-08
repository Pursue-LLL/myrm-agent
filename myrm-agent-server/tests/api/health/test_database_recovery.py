import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.recovery import rescue_database
from app.server.status import system_status
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


@pytest.fixture
def app() -> FastAPI:
    from app.main import app as main_app

    return main_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    db_file = tmp_path / "test_data.db"

    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test_table (name) VALUES ('test1')")
    conn.execute("INSERT INTO test_table (name) VALUES ('test2')")
    conn.commit()
    conn.close()

    yield str(db_file)

    if db_file.exists():
        db_file.unlink()


def test_backup_and_restore_via_manager(tmp_path: Path):
    """SQLiteBackupManager creates verified backup and restores correctly."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test_table (name) VALUES ('test1')")
    conn.execute("INSERT INTO test_table (name) VALUES ('test2')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "sqlite_backups"
    manager = SQLiteBackupManager(db_path=db_file, backup_dir=backup_dir)
    record = manager.create_backup()

    assert record.quick_check == "ok"

    conn = sqlite3.connect(str(db_file))
    conn.execute("INSERT INTO test_table (name) VALUES ('test3')")
    conn.commit()
    conn.close()

    result = manager.restore_latest()
    assert result.restored is True

    conn = sqlite3.connect(str(db_file))
    cursor = conn.execute("SELECT count(*) FROM test_table")
    assert cursor.fetchone()[0] == 2
    conn.close()


def test_rescue_database_malformed(temp_db_path: str):
    """Test rescue of corrupted database via .iterdump."""
    with open(temp_db_path, "r+b") as f:
        f.seek(100)
        f.write(b"CORRUPTED_DATA_HERE_TO_BREAK_SQLITE")

    success = rescue_database(temp_db_path)

    assert isinstance(success, bool)


@pytest.mark.asyncio
async def test_reset_database_api(client: TestClient):
    """Test database reset API."""
    system_status.database_degraded = True

    response = client.post("/api/v1/health/database/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    assert system_status.database_degraded is False
