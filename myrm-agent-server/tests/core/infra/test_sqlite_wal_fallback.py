import sqlite3
from pathlib import Path
from unittest.mock import patch

from app.database.factory import get_sqlite_busy_timeout_ms, set_sqlite_pragma
from app.server.status import system_status


class MockCursor:
    def __init__(self):
        self.wal_triggered = False
        self.delete_triggered = False
        self.recorded_pragmas = []

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str):
            self.recorded_pragmas.append(sql)
            if "journal_mode=WAL" in sql:
                self.wal_triggered = True
                raise sqlite3.OperationalError("disk i/o error or locking protocol violation")
            elif "journal_mode=DELETE" in sql:
                self.delete_triggered = True

    def close(self):
        pass

class MockConnection:
    def __init__(self):
        self._cursor = MockCursor()

    def cursor(self):
        return self._cursor

    def close(self):
        pass

def test_sqlite_wal_fallback_unit(tmp_path: Path):
    """Verify set_sqlite_pragma gracefully degrades to DELETE mode when WAL fails
    on network shared storage (NFS/SMB/FUSE), with adaptive busy_timeout and synchronous."""
    mock_conn = MockConnection()
    system_status.database_degraded = False

    # Point settings at a non-existent DB so on_disk_journal_mode_is_wal returns False
    fake_db = str(tmp_path / "nonexistent.db")
    base_timeout_ms = get_sqlite_busy_timeout_ms()
    with patch("app.database.factory.settings") as mock_settings:
        mock_settings.database.sqlite_path = fake_db
        mock_settings.database.sqlite_busy_timeout_ms = base_timeout_ms
        set_sqlite_pragma(mock_conn, None)

    assert mock_conn._cursor.wal_triggered is True
    assert mock_conn._cursor.delete_triggered is True
    assert system_status.database_degraded is True
    timeout_pragma = [p for p in mock_conn._cursor.recorded_pragmas if "busy_timeout" in p]
    assert len(timeout_pragma) > 0
    assert str(base_timeout_ms * 3) in timeout_pragma[0], f"Expected 3x busy_timeout ({base_timeout_ms * 3}), got {timeout_pragma[0]}"

    sync_pragma = [p for p in mock_conn._cursor.recorded_pragmas if "synchronous" in p]
    assert len(sync_pragma) > 0
    assert "NORMAL" in sync_pragma[0], f"Expected synchronous=NORMAL, got {sync_pragma[0]}"
