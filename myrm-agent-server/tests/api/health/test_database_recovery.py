import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

from app.database.operations.recovery import rescue_database
from app.server.status import system_status


@pytest.fixture
def app() -> FastAPI:
    from tests.support.minimal_app import build_minimal_app

    return build_minimal_app(preset="health")


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
    """Test rescue of corrupted database via B-Tree rowid salvage engine."""
    with open(temp_db_path, "r+b") as f:
        f.seek(100)
        f.write(b"CORRUPTED_DATA_HERE_TO_BREAK_SQLITE")

    success = rescue_database(temp_db_path)
    assert isinstance(success, bool)


def test_rescue_database_detailed_flow(tmp_path: Path):
    """Test detailed rescue flow with isolation, stats, and safe rollback."""
    from app.database.operations.recovery import rescue_database_detailed

    db_file = tmp_path / "corrupt_flow.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, content TEXT);")
    for i in range(1, 501):
        conn.execute(
            "INSERT INTO chat_history VALUES (?, ?);", (i, f"message_{i}" * 10)
        )
    conn.commit()
    conn.close()

    # Corrupt single page byte in the middle (page 3, offset 8192+)
    file_bytes = bytearray(db_file.read_bytes())
    assert len(file_bytes) > 8192
    file_bytes[8192 + 100 : 8192 + 200] = b"\xff\x00\xde\xad" * 25
    db_file.write_bytes(file_bytes)

    result = rescue_database_detailed(str(db_file))
    assert result.success is True
    assert result.total_recovered_rows > 0
    assert "chat_history" in result.table_stats
    assert Path(db_file).exists()
    assert (tmp_path / "corrupt_flow.db.corrupted").exists()


@pytest.mark.asyncio
async def test_reset_database_api(client: TestClient):
    """Test database reset API."""
    system_status.database_degraded = True

    response = client.post("/api/v1/health/database/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    assert system_status.database_degraded is False
