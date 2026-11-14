"""SQLite connection policy of the Dev Gate store: the shared busy timeout and the write-transaction retry."""

from __future__ import annotations

import os
import random
import sqlite3
import time
from pathlib import Path

_WAL_SWITCH_TIMEOUT_SEC = 30.0


def begin_immediate(connection: sqlite3.Connection) -> None:
    for attempt in range(20):
        try:
            connection.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= 19:
                raise
            time.sleep(min(0.05 * (2**attempt), 3.0))


def enable_wal(connection: sqlite3.Connection) -> None:
    """Switch the database to WAL, retrying while another connection holds the file.

    Switching a database that is not in WAL yet needs the file exclusively. When another connection is switching or
    reading at that moment SQLite answers "database is locked" immediately instead of calling the busy handler, so the
    connect timeout never applies and concurrent first opens of a fresh database fail. Retrying with jitter lets them
    through within milliseconds; a database that is already in WAL returns on the first attempt.
    """
    deadline = time.monotonic() + _WAL_SWITCH_TIMEOUT_SEC
    while True:
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(random.uniform(0.01, 0.05))


def dev_gate_sqlite_busy_timeout_ms() -> int:
    override = os.environ.get("MYRM_DEV_GATE_BUSY_TIMEOUT_MS", "").strip()
    if override.isdigit():
        return max(1000, int(override))
    burst_flag = Path(os.environ.get("TMPDIR", "/tmp")) / "myrm-phase-c-burst-active"
    try:
        if burst_flag.is_file() and (time.time() - burst_flag.stat().st_mtime) < 7200.0:
            return 5000
    except OSError:
        pass
    return 30000
