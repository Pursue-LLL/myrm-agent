"""A ledger created before the registering server was recorded gets the new columns when it is opened."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background import job_store as job_store_module
from myrm_agent_harness.agent.meta_tools.bash._background.job_store import BackgroundJobStore
from myrm_agent_harness.agent.meta_tools.bash._background.termination import GroupMember

# The table as it was first defined, before the registering server was recorded.
_FIRST_TABLE = """
    CREATE TABLE background_jobs (
        job_id TEXT PRIMARY KEY,
        pid INTEGER,
        session_id TEXT NOT NULL,
        command TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at REAL NOT NULL,
        completed_at REAL,
        exit_code INTEGER,
        error_category TEXT,
        finish_processed INTEGER NOT NULL DEFAULT 0,
        vault_log_ref TEXT,
        updated_at REAL NOT NULL
    )
"""


def _columns(db_path: Path) -> list[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [row[1] for row in conn.execute("PRAGMA table_info(background_jobs)")]


def test_a_ledger_without_the_server_columns_gets_them_and_keeps_its_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "first.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_FIRST_TABLE)
        conn.execute(
            "INSERT INTO background_jobs (job_id, pid, session_id, command, status, started_at, updated_at)"
            " VALUES ('job-first', 31, 'chat-1', 'serve', 'running', 1.0, 1.0)"
        )

    migrated = BackgroundJobStore(db_path)

    first = migrated.get_by_job_id("job-first")
    assert first is not None
    assert (first.status, first.owner_pid, first.owner_start_stamp) == ("running", None, None)
    migrated.insert_running(
        job_id="job-next",
        pid=100,
        session_id="chat-1",
        command="cmd",
        started_at=1.0,
        owner=GroupMember(pid=77, start_stamp=12.5),
    )
    next_job = migrated.get_by_job_id("job-next")
    assert next_job is not None
    assert (next_job.owner_pid, next_job.owner_start_stamp) == (77, 12.5)
    BackgroundJobStore(db_path)
    columns = _columns(db_path)
    assert columns.count("owner_pid") == 1
    assert columns.count("owner_start_stamp") == 1


def test_a_new_ledger_has_the_same_columns_as_a_migrated_one(tmp_path: Path) -> None:
    migrated_path = tmp_path / "migrated.db"
    with closing(sqlite3.connect(migrated_path)) as conn, conn:
        conn.execute(_FIRST_TABLE)
    BackgroundJobStore(migrated_path)
    fresh_path = tmp_path / "fresh.db"
    BackgroundJobStore(fresh_path)

    assert _columns(migrated_path) == _columns(fresh_path)
    assert {"owner_pid", "owner_start_stamp"} <= set(_columns(fresh_path))


def _connection_whose_alter_fails(message: str) -> MagicMock:
    conn = MagicMock(spec=sqlite3.Connection)

    def execute(statement: str) -> list[dict[str, str]]:
        if statement.startswith("PRAGMA"):
            return [{"name": "job_id"}]
        raise sqlite3.OperationalError(message)

    conn.execute.side_effect = execute
    return conn


def test_a_column_a_second_server_added_in_the_meantime_is_not_an_error() -> None:
    job_store_module._add_missing_columns(_connection_whose_alter_fails("duplicate column name: owner_pid"))


def test_any_other_failure_to_add_a_column_is_raised() -> None:
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        job_store_module._add_missing_columns(_connection_whose_alter_fails("database is locked"))
