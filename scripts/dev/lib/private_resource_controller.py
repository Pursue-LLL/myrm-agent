"""Single credit-based admission queue for PRIVATE Chrome E2E runtimes."""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass

from dev_gate_contract import LIVE_SHPOIB_MAX_CONCURRENT
from dev_gate_session import SessionState
from dev_gate_store import DevGateStore, _begin_immediate

PRIVATE_ADMIT_TIMEOUT_SEC = 900.0
PRIVATE_QUEUE_PROGRESS_SEC = 30.0
PRIVATE_AGING_INTERVAL_SEC = 60.0
PRIVATE_CAPACITY_MAX = LIVE_SHPOIB_MAX_CONCURRENT  # S2: single cap source

_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS private_admission (
    session_id TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    credits INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    enqueued_at REAL NOT NULL,
    granted_at REAL,
    released_at REAL
);
CREATE INDEX IF NOT EXISTS private_admission_wait_idx
ON private_admission(granted_at, released_at, enqueued_at);
"""


@dataclass(frozen=True, slots=True)
class PrivateAdmission:
    granted: bool
    queue_position: int
    active_credits: int
    capacity_credits: int
    waited_sec: float
    next_progress_sec: float
    idle_reason: str = ""
    available_credits: int = 0


def private_capacity_credits() -> int:
    """Return Host Governor effective cap (same pressure snapshot as browser dispatch)."""
    override = os.environ.get("MYRM_PRIVATE_CAPACITY_CREDITS", "").strip()
    if override:
        capacity = int(override)
        if not 1 <= capacity <= PRIVATE_CAPACITY_MAX:
            raise ValueError(
                "MYRM_PRIVATE_CAPACITY_CREDITS must be between "
                f"1 and {PRIVATE_CAPACITY_MAX}"
            )
        return capacity
    try:
        from host_resource_governor import effective_private_capacity_credits

        return min(PRIVATE_CAPACITY_MAX, effective_private_capacity_credits())
    except ImportError:
        cpu_count = os.cpu_count() or 1
        cpu_capacity = max(1, cpu_count // 2)
        memory_capacity = PRIVATE_CAPACITY_MAX
        try:
            available_bytes = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
            memory_capacity = max(1, int(available_bytes // (2 * 1024**3)))
        except (OSError, ValueError):
            pass
        return min(PRIVATE_CAPACITY_MAX, cpu_capacity, memory_capacity)


class PrivateResourceController:
    def __init__(self, store: DevGateStore, *, capacity_credits: int) -> None:
        if capacity_credits < 1:
            raise ValueError("capacity_credits must be positive")
        self.store = store
        self.capacity_credits = capacity_credits
        with self._connect() as connection:
            connection.executescript(_QUEUE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def admit(
        self,
        session_id: str,
        owner_token: str,
        *,
        now: float | None = None,
    ) -> PrivateAdmission:
        admitted_at = time.time() if now is None else now
        with self._connect() as connection:
            _begin_immediate(connection)
            self._release_terminal_sessions(connection, admitted_at)
            session = self._owned_private_session(connection, session_id, owner_token)
            connection.execute(
                """
                INSERT INTO private_admission(
                    session_id, owner_token, credits, priority, enqueued_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (
                    session_id,
                    owner_token,
                    int(session["private_credits"]),
                    int(session["priority"]),
                    admitted_at,
                ),
            )
            queued = self._queue_row(connection, session_id)
            waited = max(0.0, admitted_at - float(queued["enqueued_at"]))
            if queued["granted_at"] is None and waited >= PRIVATE_ADMIT_TIMEOUT_SEC:
                self._fail_timeout(connection, session, admitted_at)
                connection.commit()
                raise TimeoutError(
                    f"PRIVATE_ADMIT_TIMEOUT: session={session_id} "
                    f"waited={int(waited)}s"
                )
            self._grant_waiters(connection, admitted_at)
            queued = self._queue_row(connection, session_id)
            active = self._active_credits(connection)
            if queued["granted_at"] is not None:
                idle = self._credit_idle_reason(
                    active_credits=active,
                    available_credits=max(0, self.capacity_credits - active),
                    waiting_rows=self._ordered_waiters(connection, admitted_at),
                )
                return PrivateAdmission(
                    granted=True,
                    queue_position=0,
                    active_credits=active,
                    capacity_credits=self.capacity_credits,
                    waited_sec=waited,
                    next_progress_sec=0.0,
                    idle_reason=idle,
                    available_credits=max(0, self.capacity_credits - active),
                )
            position = self._queue_position(connection, session_id, admitted_at)
            next_progress = PRIVATE_QUEUE_PROGRESS_SEC - (
                waited % PRIVATE_QUEUE_PROGRESS_SEC
            )
            idle = self._credit_idle_reason(
                active_credits=active,
                available_credits=max(0, self.capacity_credits - active),
                waiting_rows=self._ordered_waiters(connection, admitted_at),
            )
            return PrivateAdmission(
                granted=False,
                queue_position=position,
                active_credits=active,
                capacity_credits=self.capacity_credits,
                waited_sec=waited,
                next_progress_sec=next_progress,
                idle_reason=idle,
                available_credits=max(0, self.capacity_credits - active),
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
                raise PermissionError(f"private admission owner mismatch: {session_id}")
            connection.execute(
                """
                UPDATE private_admission SET released_at=?
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
                    active = self._active_credits(connection)
                    waiting = connection.execute(
                        """
                        SELECT session_id, credits, priority, enqueued_at
                        FROM private_admission
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
            raise RuntimeError("private admission snapshot failed")
        available = max(0, self.capacity_credits - active)
        idle_reason = self._credit_idle_reason(
            active_credits=active,
            available_credits=available,
            waiting_rows=waiting,
        )
        return {
            "capacity_credits": self.capacity_credits,
            "active_credits": active,
            "available_credits": available,
            "idle_reason": idle_reason,
            "waiting": [
                {
                    "session_id": str(row["session_id"]),
                    "credits": int(row["credits"]),
                    "priority": int(row["priority"]),
                    "waited_sec": max(0.0, captured_at - float(row["enqueued_at"])),
                }
                for row in waiting
            ],
        }

    @staticmethod
    def _credit_idle_reason(
        *,
        active_credits: int,
        available_credits: int,
        waiting_rows: list[sqlite3.Row],
    ) -> str:
        if available_credits <= 0:
            return "capacity_full"
        if not waiting_rows:
            return "available"
        min_wait_credits = min(int(row["credits"]) for row in waiting_rows)
        if min_wait_credits > available_credits:
            return "head_blocked_large_reservation"
        return "backfill_eligible"

    @staticmethod
    def _release_terminal_sessions(
        connection: sqlite3.Connection,
        now: float,
    ) -> None:
        connection.execute(
            """
            UPDATE private_admission SET released_at=?
            WHERE released_at IS NULL AND session_id IN (
                SELECT session_id FROM sessions
                WHERE state IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
            )
            """,
            (now,),
        )
        from owner_identity import owner_process_matches

        active_rows = connection.execute(
            """
            SELECT pa.session_id, s.owner_pid, s.owner_process_start, s.state
            FROM private_admission pa
            JOIN sessions s ON s.session_id = pa.session_id
            WHERE pa.granted_at IS NOT NULL
              AND pa.released_at IS NULL
              AND s.state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
            """
        ).fetchall()
        abandoned: list[str] = []
        for row in active_rows:
            owner_pid = int(row["owner_pid"])
            owner_start = str(row["owner_process_start"])
            if owner_process_matches(pid=owner_pid, expected_start=owner_start):
                continue
            abandoned.append(str(row["session_id"]))
        if abandoned:
            placeholders = ",".join("?" for _ in abandoned)
            connection.execute(
                f"""
                UPDATE private_admission SET released_at=?
                WHERE released_at IS NULL AND session_id IN ({placeholders})
                """,
                (now, *abandoned),
            )

    @staticmethod
    def _queue_row(
        connection: sqlite3.Connection,
        session_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM private_admission WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"private admission not found: {session_id}")
        return row

    @staticmethod
    def _owned_private_session(
        connection: sqlite3.Connection,
        session_id: str,
        owner_token: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"session not found: {session_id}")
        if str(row["owner_token"]) != owner_token:
            raise PermissionError(f"session owner mismatch: {session_id}")
        if str(row["execution_mode"]) != "PRIVATE":
            raise ValueError(
                f"shared session cannot enter private admission: {session_id}"
            )
        if str(row["state"]) not in {
            SessionState.PRIVATE_ADMIT.value,
            SessionState.PREPARING.value,
        }:
            raise ValueError(
                f"session is not admissible: {session_id} state={row['state']}"
            )
        return row

    @staticmethod
    def _active_credits(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(credits), 0) AS total
            FROM private_admission
            WHERE granted_at IS NOT NULL AND released_at IS NULL
            """
        ).fetchone()
        return 0 if row is None else int(row["total"])

    def _ordered_waiters(
        self,
        connection: sqlite3.Connection,
        now: float,
    ) -> list[sqlite3.Row]:
        return list(
            connection.execute(
                """
                SELECT *,
                    priority + CAST((? - enqueued_at) / ? AS INTEGER)
                    AS effective_priority
                FROM private_admission
                WHERE granted_at IS NULL AND released_at IS NULL
                ORDER BY effective_priority DESC, enqueued_at ASC, session_id ASC
                """,
                (now, PRIVATE_AGING_INTERVAL_SEC),
            ).fetchall()
        )

    def _grant_waiters(
        self,
        connection: sqlite3.Connection,
        now: float,
    ) -> tuple[str, ...]:
        available = self.capacity_credits - self._active_credits(connection)
        granted: list[str] = []
        for waiter in self._ordered_waiters(connection, now):
            credits = int(waiter["credits"])
            if credits > available:
                continue
            session_id = str(waiter["session_id"])
            session = connection.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if session is None or str(session["state"]) != "PRIVATE_ADMIT":
                continue
            version = int(session["version"]) + 1
            connection.execute(
                """
                UPDATE private_admission SET granted_at=? WHERE session_id=?
                """,
                (now, session_id),
            )
            # Preserve submit wall budget: grant must cover remaining bootstrap+BODY after
            # queue wait (log-8: flat now+600 caused HARD_DEADLINE mid mux recovery).
            existing_deadline = float(session["hard_deadline"])
            from dev_gate_contract import (
                dev_gate_post_admit_hard_timeout_sec,
            )  # noqa: PLC0415

            post_admit_budget = float(dev_gate_post_admit_hard_timeout_sec())
            new_hard_deadline = max(existing_deadline, now + post_admit_budget)
            connection.execute(
                """
                UPDATE sessions SET state='PREPARING', version=?,
                    phase_started_at=?, last_progress_at=?,
                    hard_deadline=?
                WHERE session_id=?
                """,
                (version, now, now, new_hard_deadline, session_id),
            )
            connection.execute(
                """
                INSERT INTO events(
                    session_id, version, event_type, state, created_at, detail_json
                ) VALUES (?, ?, 'PRIVATE_ADMIT_GRANTED', 'PREPARING', ?, ?)
                """,
                (
                    session_id,
                    version,
                    now,
                    f'{{"credits":{credits}}}',
                ),
            )
            available -= credits
            granted.append(session_id)
        return tuple(granted)

    def _queue_position(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        now: float,
    ) -> int:
        waiters = self._ordered_waiters(connection, now)
        for index, row in enumerate(waiters, start=1):
            if str(row["session_id"]) == session_id:
                return index
        return 0

    @staticmethod
    def _fail_timeout(
        connection: sqlite3.Connection,
        session: sqlite3.Row,
        now: float,
    ) -> None:
        session_id = str(session["session_id"])
        version = int(session["version"]) + 1
        connection.execute(
            """
            UPDATE sessions SET state='FAILED', version=?, failure_token=?,
                phase_started_at=?, last_progress_at=?
            WHERE session_id=?
            """,
            (version, "PRIVATE_ADMIT_TIMEOUT", now, now, session_id),
        )
        connection.execute(
            "UPDATE private_admission SET released_at=? WHERE session_id=?",
            (now, session_id),
        )
