"""SQLite connection policy of the Dev Gate store: the shared busy timeout and the write-transaction retry."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def begin_immediate(connection: sqlite3.Connection) -> None:
    for attempt in range(20):
        try:
            connection.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= 19:
                raise
            time.sleep(min(0.05 * (2**attempt), 3.0))


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
