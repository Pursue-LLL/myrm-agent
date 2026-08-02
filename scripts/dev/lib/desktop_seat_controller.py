"""Single macOS GUI seat admission for DESKTOP workload Chrome E2E."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from dataclasses import dataclass

from dev_gate_session import SessionState, TERMINAL_STATES, Workload
from dev_gate_store import DevGateStore, _begin_immediate

DESKTOP_SEAT_TIMEOUT_SEC = 900.0
DESKTOP_SEAT_QUEUE_PROGRESS_SEC = 30.0
DESKTOP_SEAT_CAPACITY = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS desktop_seat_admission (
    session_id TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    enqueued_at REAL NOT NULL,
    granted_at REAL,
    released_at REAL
);
CREATE INDEX IF NOT EXISTS desktop_seat_wait_idx
ON desktop_seat_admission(granted_at, released_at, enqueued_at);
"""


@dataclass(frozen=True, slots=True)
class DesktopSeatAdmission:
    granted: bool
    queue_position: int
    active_seats: int
    capacity_seats: int
    waited_sec: float
    next_progress_sec: float


def desktop_seat_capacity() -> int:
    if sys.platform != "darwin":
        return 0
    override = os.environ.get("MYRM_DESKTOP_SEAT_CAPACITY", "").strip()
    if override:
        capacity = int(override)
        if capacity not in {0, 1}:
            raise ValueError("MYRM_DESKTOP_SEAT_CAPACITY must be 0 or 1")
        return capacity
    return DESKTOP_SEAT_CAPACITY


class DesktopSeatController:
    def __init__(self, store: DevGateStore, *, capacity_seats: int) -> None:
        if capacity_seats not in {0, 1}:
            raise ValueError("capacity_seats must be 0 or 1")
        self.store = store
        self.capacity_seats = capacity_seats
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def admit(
        self,
        session_id: str,
        owner_token: str,
        *,
        now: float | None = None,
    ) -> DesktopSeatAdmission:
        admitted_at = time.time() if now is None else now
        if self.capacity_seats < 1:
            return DesktopSeatAdmission(
                granted=True,
                queue_position=0,
                active_seats=0,
                capacity_seats=0,
                waited_sec=0.0,
                next_progress_sec=0.0,
            )
        record = self.store.get(session_id)
        if record is None or record.owner_token != owner_token:
            raise PermissionError(f"desktop seat owner mismatch: {session_id}")
        if record.policy.workload is not Workload.DESKTOP:
            raise ValueError(f"desktop seat requires DESKTOP workload: {session_id}")
        with self._connect() as connection:
            _begin_immediate(connection)
            self._release_terminal_sessions(connection, admitted_at)
            connection.execute(
                """
                INSERT INTO desktop_seat_admission(
                    session_id, owner_token, enqueued_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (session_id, owner_token, admitted_at),
            )
            row = self._queue_row(connection, session_id)
            waited = max(0.0, admitted_at - float(row["enqueued_at"]))
            if row["granted_at"] is None and waited >= DESKTOP_SEAT_TIMEOUT_SEC:
                connection.execute(
                    """
                    UPDATE desktop_seat_admission SET released_at=?
                    WHERE session_id=? AND released_at IS NULL
                    """,
                    (admitted_at, session_id),
                )
                connection.commit()
                raise TimeoutError(
                    f"DESKTOP_SEAT_TIMEOUT: session={session_id} waited={int(waited)}s"
                )
            self._grant_waiters(connection, admitted_at)
            row = self._queue_row(connection, session_id)
            active = self._active_seats(connection)
            if row["granted_at"] is not None:
                return DesktopSeatAdmission(
                    granted=True,
                    queue_position=0,
                    active_seats=active,
                    capacity_seats=self.capacity_seats,
                    waited_sec=waited,
                    next_progress_sec=0.0,
                )
            position = self._queue_position(connection, session_id)
            next_progress = DESKTOP_SEAT_QUEUE_PROGRESS_SEC - (
                waited % DESKTOP_SEAT_QUEUE_PROGRESS_SEC
            )
            return DesktopSeatAdmission(
                granted=False,
                queue_position=position,
                active_seats=active,
                capacity_seats=self.capacity_seats,
                waited_sec=waited,
                next_progress_sec=next_progress,
            )

    def release(
        self,
        session_id: str,
        owner_token: str,
        *,
        now: float | None = None,
    ) -> tuple[str, ...]:
        released_at = time.time() if now is None else now
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._queue_row(connection, session_id)
            if str(row["owner_token"]) != owner_token:
                raise PermissionError(f"desktop seat owner mismatch: {session_id}")
            connection.execute(
                """
                UPDATE desktop_seat_admission SET released_at=?
                WHERE session_id=? AND released_at IS NULL
                """,
                (released_at, session_id),
            )
            return self._grant_waiters(connection, released_at)

    def snapshot(self, *, now: float | None = None) -> dict[str, object]:
        captured_at = time.time() if now is None else now
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(8):
            try:
                with self._connect() as connection:
                    _begin_immediate(connection)
                    self._release_terminal_sessions(connection, captured_at)
                    active = self._active_seats(connection)
                    waiting = connection.execute(
                        """
                        SELECT session_id, enqueued_at
                        FROM desktop_seat_admission
                        WHERE granted_at IS NULL AND released_at IS NULL
                        ORDER BY enqueued_at, session_id
                        """
                    ).fetchall()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= 7:
                    raise
                last_error = exc
                time.sleep(min(0.25 * (2**attempt), 2.0))
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError("desktop seat snapshot failed")
        return {
            "capacity_seats": self.capacity_seats,
            "active_seats": active,
            "waiting": [
                {
                    "session_id": str(row["session_id"]),
                    "waited_sec": max(0.0, captured_at - float(row["enqueued_at"])),
                }
                for row in waiting
            ],
        }

    def _release_terminal_sessions(
        self, connection: sqlite3.Connection, now: float
    ) -> None:
        terminal_values = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ",".join("?" for _ in terminal_values)
        rows = connection.execute(
            f"""
            SELECT s.session_id
            FROM sessions AS s
            INNER JOIN desktop_seat_admission AS d ON d.session_id = s.session_id
            WHERE s.state IN ({placeholders})
              AND d.granted_at IS NOT NULL
              AND d.released_at IS NULL
            """,
            terminal_values,
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE desktop_seat_admission SET released_at=?
                WHERE session_id=? AND released_at IS NULL
                """,
                (now, str(row["session_id"])),
            )

    def _active_seats(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total FROM desktop_seat_admission
            WHERE granted_at IS NOT NULL AND released_at IS NULL
            """
        ).fetchone()
        return int(row["total"]) if row is not None else 0

    def _queue_row(
        self, connection: sqlite3.Connection, session_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT session_id, owner_token, enqueued_at, granted_at, released_at
            FROM desktop_seat_admission WHERE session_id=?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"desktop seat queue row missing: {session_id}")
        return row

    def _queue_position(self, connection: sqlite3.Connection, session_id: str) -> int:
        rows = connection.execute(
            """
            SELECT session_id FROM desktop_seat_admission
            WHERE granted_at IS NULL AND released_at IS NULL
            ORDER BY enqueued_at, session_id
            """
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            if str(row["session_id"]) == session_id:
                return index
        return 0

    def _grant_waiters(
        self, connection: sqlite3.Connection, now: float
    ) -> tuple[str, ...]:
        granted: list[str] = []
        while self._active_seats(connection) < self.capacity_seats:
            row = connection.execute(
                """
                SELECT session_id FROM desktop_seat_admission
                WHERE granted_at IS NULL AND released_at IS NULL
                ORDER BY enqueued_at, session_id LIMIT 1
                """
            ).fetchone()
            if row is None:
                break
            session_id = str(row["session_id"])
            connection.execute(
                """
                UPDATE desktop_seat_admission SET granted_at=?
                WHERE session_id=? AND granted_at IS NULL AND released_at IS NULL
                """,
                (now, session_id),
            )
            granted.append(session_id)
        return tuple(granted)
