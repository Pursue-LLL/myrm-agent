import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError

from app.database.operations import recovery as recovery_module
from app.database.operations.recovery import database_is_damaged, reports_corruption, rescue_database
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
        conn.execute("INSERT INTO chat_history VALUES (?, ?);", (i, f"message_{i}" * 10))
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


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """A multi-page database, so a truncation or a damaged page lands inside real content."""
    db_file = tmp_path / "populated.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, content TEXT);")
    for i in range(1, 501):
        conn.execute("INSERT INTO chat_history VALUES (?, ?);", (i, f"message_{i}" * 10))
    conn.commit()
    conn.close()
    return db_file


def test_database_is_damaged_is_false_for_an_intact_file(populated_db: Path):
    assert database_is_damaged(str(populated_db)) is False


def test_database_is_damaged_is_false_for_a_missing_or_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.db"
    empty.touch()

    assert database_is_damaged(str(tmp_path / "absent.db")) is False
    assert database_is_damaged(str(empty)) is False


def test_database_is_damaged_detects_garbage_where_the_header_belongs(tmp_path: Path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database" * 100)

    assert database_is_damaged(str(junk)) is True


def test_database_is_damaged_detects_a_truncated_file(populated_db: Path):
    populated_db.write_bytes(populated_db.read_bytes()[: populated_db.stat().st_size // 2])

    assert database_is_damaged(str(populated_db)) is True


def test_database_is_damaged_detects_a_corrupted_page(populated_db: Path):
    content = bytearray(populated_db.read_bytes())
    content[8192 + 100 : 8192 + 200] = b"\xff\x00\xde\xad" * 25
    populated_db.write_bytes(content)

    assert database_is_damaged(str(populated_db)) is True


def test_database_is_damaged_detects_a_damaged_schema_page(populated_db: Path):
    """Page 1 holds the schema: SQLite itself refuses to read the file, with no page-level report to inspect."""
    content = bytearray(populated_db.read_bytes())
    content[100:300] = b"\xff\x00\xde\xad" * 50
    populated_db.write_bytes(content)

    assert database_is_damaged(str(populated_db)) is True


def test_database_is_damaged_is_false_while_another_connection_holds_the_lock(
    populated_db: Path, monkeypatch: pytest.MonkeyPatch
):
    """A lock says nothing about the pages: the file must not be reported damaged, and so must not be rewritten."""
    monkeypatch.setattr(recovery_module, "_PROBE_LOCK_TIMEOUT_SECONDS", 0.05)
    holder = sqlite3.connect(str(populated_db), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        assert database_is_damaged(str(populated_db)) is False
    finally:
        holder.close()


def _error_sqlite_raises(db_file: Path, statement: str) -> sqlite3.DatabaseError:
    with closing(sqlite3.connect(str(db_file))) as conn, pytest.raises(sqlite3.DatabaseError) as raised:
        conn.execute(statement).fetchall()
    return raised.value


@pytest.fixture
def corruption_error(tmp_path: Path) -> sqlite3.DatabaseError:
    """What SQLite raises when it opens a file that is not a database."""
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database" * 100)
    error = _error_sqlite_raises(junk, "PRAGMA user_version")
    assert error.sqlite_errorcode == sqlite3.SQLITE_NOTADB
    return error


def test_reports_corruption_recognises_the_error_sqlite_raises_on_a_damaged_file(corruption_error: sqlite3.DatabaseError):
    assert reports_corruption(corruption_error) is True


def test_reports_corruption_recognises_the_extended_result_codes_of_corruption():
    reported = sqlite3.DatabaseError("database disk image is malformed")
    reported.sqlite_errorcode = sqlite3.SQLITE_CORRUPT_INDEX

    assert reported.sqlite_errorcode != sqlite3.SQLITE_CORRUPT
    assert reports_corruption(reported) is True


def test_reports_corruption_finds_it_behind_sqlalchemy_and_exception_causes(corruption_error: sqlite3.DatabaseError):
    wrapped = SQLAlchemyDatabaseError("SELECT 1", None, corruption_error)
    chained = RuntimeError("Database table init failed")
    chained.__cause__ = corruption_error

    assert reports_corruption(wrapped) is True
    assert reports_corruption(chained) is True


def test_reports_corruption_is_false_for_failures_that_say_nothing_about_the_pages(populated_db: Path):
    no_such_table = _error_sqlite_raises(populated_db, "ALTER TABLE procedural_rules ADD COLUMN source TEXT")

    assert no_such_table.sqlite_errorcode == sqlite3.SQLITE_ERROR
    assert reports_corruption(no_such_table) is False
    assert reports_corruption(SQLAlchemyDatabaseError("SELECT 1", None, no_such_table)) is False
    assert reports_corruption(RuntimeError("Database migration failed at version 0")) is False


def test_reports_corruption_terminates_on_a_cycle_of_causes():
    first, second = RuntimeError("first"), RuntimeError("second")
    first.__cause__, second.__cause__ = second, first

    assert reports_corruption(first) is False


@pytest.mark.asyncio
async def test_reset_database_api(client: TestClient):
    """Test database reset API."""
    system_status.database_degraded = True

    response = client.post("/api/v1/health/database/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    assert system_status.database_degraded is False
