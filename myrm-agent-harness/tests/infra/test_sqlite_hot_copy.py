"""hot_copy_database copies a live database to a standalone file, also while another connection keeps committing."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from myrm_agent_harness.infra.sqlite_backup import hot_copy_database

_ROW_BYTES = 3_900
# About 24 MB: a copy in page batches needs dozens of uninterrupted steps, which a steady writer never allows.
_ROWS = 6_000
_COPY_DEADLINE_S = 15.0


@dataclass
class _WriterReport:
    commits: int = 0
    errors: list[sqlite3.Error] = field(default_factory=list)


def _grow_database(path: Path, journal_mode: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, payload BLOB)")
    blob = os.urandom(_ROW_BYTES)
    conn.executemany("INSERT INTO items (payload) VALUES (?)", [(blob,)] * _ROWS)
    conn.commit()
    conn.close()


@contextmanager
def _committing_writer(path: Path) -> Iterator[_WriterReport]:
    """Another connection that commits one small row every millisecond, the way a busy application does."""
    stop = threading.Event()
    report = _WriterReport()

    def commit_until_stopped() -> None:
        conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
        try:
            while not stop.is_set():
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("INSERT INTO items (payload) VALUES (zeroblob(16))")
                    conn.execute("COMMIT")
                    report.commits += 1
                except sqlite3.Error as exc:
                    report.errors.append(exc)
                    break
                time.sleep(0.001)
        finally:
            conn.close()

    writer = threading.Thread(target=commit_until_stopped, daemon=True)
    writer.start()
    try:
        yield report
    finally:
        stop.set()
        writer.join(timeout=10)


def _assert_standalone_copy(copy: Path, at_least_rows: int) -> None:
    assert not list(copy.parent.glob(f"{copy.name}-*")), "a copy must not leave WAL/SHM siblings"
    conn = sqlite3.connect(str(copy))
    try:
        assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
        count, highest_id = conn.execute("SELECT count(*), max(id) FROM items").fetchone()
        assert count >= at_least_rows
        assert count == highest_id, "the rows of one commit sequence must be a gap-free prefix"
    finally:
        conn.close()


@pytest.mark.parametrize("journal_mode", ["WAL", "DELETE"])
def test_a_copy_finishes_while_another_connection_commits_continuously(tmp_path: Path, journal_mode: str) -> None:
    live, copy = tmp_path / "live.db", tmp_path / "copy.db"
    _grow_database(live, journal_mode)
    finished = threading.Event()
    failures: list[BaseException] = []

    def copy_database() -> None:
        try:
            hot_copy_database(live, copy)
        except BaseException as exc:  # reported by the assertions below, not lost in the thread
            failures.append(exc)
        finally:
            finished.set()

    with _committing_writer(live) as writer:
        threading.Thread(target=copy_database, daemon=True).start()
        copied_while_committing = finished.wait(timeout=_COPY_DEADLINE_S)
    # Once the writer has stopped even a copy that kept restarting completes, so no thread outlives the test.
    assert finished.wait(timeout=_COPY_DEADLINE_S)

    assert copied_while_committing, "the copy kept restarting while commits landed"
    assert not failures
    assert not writer.errors, "the writer must wait for the copy, not fail"
    assert writer.commits > 0
    _assert_standalone_copy(copy, at_least_rows=_ROWS)


@pytest.mark.parametrize("journal_mode", ["WAL", "DELETE"])
def test_an_idle_copy_holds_every_committed_row(tmp_path: Path, journal_mode: str) -> None:
    live, copy = tmp_path / "live.db", tmp_path / "copy.db"
    _grow_database(live, journal_mode)

    hot_copy_database(live, copy)

    _assert_standalone_copy(copy, at_least_rows=_ROWS)
    conn = sqlite3.connect(str(copy))
    try:
        assert conn.execute("SELECT count(*) FROM items").fetchone() == (_ROWS,)
    finally:
        conn.close()
