"""Removal of abandoned and expired sessions, and journal compaction."""

from __future__ import annotations

import json
import time

from dev_gate.session import SessionState
from dev_gate.store.base import StoreBase
from dev_gate.store.connection import begin_immediate
from dev_gate.store.schema import DEFAULT_JOURNAL_RETENTION_SEC


class ReaperMixin(StoreBase):
    """Operations that reclaim sessions whose owner is gone or whose deadline passed."""

    def reap_abandoned(self, *, now: float | None = None) -> tuple[str, ...]:
        """Fail sessions whose owning process is gone and make cleanup auditable."""
        reaped_at = time.time() if now is None else now
        reaped: list[str] = []
        with self._connect() as connection:
            begin_immediate(connection)
            terminal = (
                SessionState.SUCCEEDED.value,
                SessionState.FAILED.value,
                SessionState.CANCELLED.value,
            )
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE state NOT IN (?, ?, ?)
                """,
                terminal,
            ).fetchall()
            for row in rows:
                owner_pid = int(row["owner_pid"])
                owner_start = str(row["owner_process_start"])
                from dev_gate.owner_identity import owner_process_matches

                if owner_process_matches(pid=owner_pid, expected_start=owner_start):
                    continue
                session_id = str(row["session_id"])
                try:
                    existing_cleanup = json.loads(str(row["cleanup_json"] or "{}"))
                except json.JSONDecodeError:
                    existing_cleanup = {}
                if existing_cleanup.get("ledger_cleaned") is True:
                    continue
                version = int(row["version"]) + 1
                cleanup = {
                    "closed_page_ids": [],
                    "closed_context_id": str(row["browser_context_id"]),
                    "released_lease_id": str(row["lease_id"]),
                    "released_runtime_id": str(row["runtime_id"]),
                    "ledger_cleaned": False,
                    "sealed": False,
                    "requested_at": reaped_at,
                    "observed_at": 0.0,
                    "completed_at": reaped_at,
                }
                connection.execute(
                    """
                    UPDATE sessions SET state='FAILED', version=?,
                        outcome='FAILED', failure_token='OWNER_EXITED',
                        cleanup_json=?, phase_started_at=?, last_progress_at=?
                    WHERE session_id=?
                    """,
                    (
                        version,
                        json.dumps(cleanup, separators=(",", ":"), sort_keys=True),
                        reaped_at,
                        reaped_at,
                        session_id,
                    ),
                )
                self._event(
                    connection,
                    session_id=session_id,
                    version=version,
                    event_type="REAP_OWNER_EXITED",
                    state=SessionState.FAILED,
                    detail={"owner_pid": owner_pid},
                    now=reaped_at,
                )
                reaped.append(session_id)
        return tuple(reaped)

    def reap_expired_deadlines(self, *, now: float | None = None) -> tuple[str, ...]:
        """Fail sessions past coordinator hard_deadline (P0-A 600s enforcement).

        Excludes SUBMITTED and PRIVATE_ADMIT: admission queue wait (up to 900s)
        must not count toward hard_deadline — only active phases (PREPARING+)
        are subject to the 600s body clock.
        """
        reaped_at = time.time() if now is None else now
        reaped: list[str] = []
        with self._connect() as connection:
            begin_immediate(connection)
            exempt = (
                SessionState.SUCCEEDED.value,
                SessionState.FAILED.value,
                SessionState.CANCELLED.value,
                SessionState.SUBMITTED.value,
                SessionState.PRIVATE_ADMIT.value,
            )
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE state NOT IN (?, ?, ?, ?, ?) AND hard_deadline <= ?
                """,
                (*exempt, reaped_at),
            ).fetchall()
            for row in rows:
                session_id = str(row["session_id"])
                version = int(row["version"]) + 1
                cleanup = {
                    "closed_page_ids": [],
                    "closed_context_id": str(row["browser_context_id"]),
                    "released_lease_id": str(row["lease_id"]),
                    "released_runtime_id": str(row["runtime_id"]),
                    "ledger_cleaned": False,
                    "sealed": False,
                    "requested_at": reaped_at,
                    "observed_at": 0.0,
                    "completed_at": reaped_at,
                }
                connection.execute(
                    """
                    UPDATE sessions SET state='FAILED', version=?,
                        outcome='FAILED', failure_token='HARD_DEADLINE',
                        cleanup_json=?, phase_started_at=?, last_progress_at=?
                    WHERE session_id=?
                    """,
                    (
                        version,
                        json.dumps(cleanup, separators=(",", ":"), sort_keys=True),
                        reaped_at,
                        reaped_at,
                        session_id,
                    ),
                )
                self._event(
                    connection,
                    session_id=session_id,
                    version=version,
                    event_type="REAP_HARD_DEADLINE",
                    state=SessionState.FAILED,
                    detail={"hard_deadline": float(row["hard_deadline"])},
                    now=reaped_at,
                )
                reaped.append(session_id)
        return tuple(reaped)

    def compact_journal(
        self,
        *,
        now: float | None = None,
        retention_sec: float = DEFAULT_JOURNAL_RETENTION_SEC,
    ) -> int:
        """Delete event journal rows older than retention window (P0-D)."""
        cutoff = (time.time() if now is None else now) - max(3600.0, retention_sec)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM events WHERE created_at < ?",
                (cutoff,),
            )
            return int(cursor.rowcount)
