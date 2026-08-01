"""SQLite WAL registry and event journal for Dev Gate Chrome E2E sessions."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from dev_gate_session import (
    AccessScope,
    CleanupReceipt,
    ExecutionMode,
    SessionOwnership,
    SessionPolicy,
    SessionRecord,
    SessionState,
    Workload,
    assert_transition,
    initial_state,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    owner_pid INTEGER NOT NULL,
    owner_token TEXT NOT NULL,
    owner_process_start TEXT NOT NULL DEFAULT '',
    owner_boot_id TEXT NOT NULL DEFAULT '',
    test_node_id TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    workload TEXT NOT NULL,
    namespace TEXT NOT NULL,
    priority INTEGER NOT NULL,
    private_credits INTEGER NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    submitted_at REAL NOT NULL,
    phase_started_at REAL NOT NULL,
    last_progress_at REAL NOT NULL,
    hard_deadline REAL NOT NULL,
    node_started_at REAL NOT NULL,
    current_node TEXT NOT NULL,
    browser_context_id TEXT NOT NULL,
    page_ids_json TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    runtime_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    failure_token TEXT NOT NULL,
    cleanup_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_state_idx ON sessions(state, submitted_at);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    detail_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_session_idx ON events(session_id, event_id);
"""

_MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE sessions ADD COLUMN owner_process_start TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN owner_boot_id TEXT NOT NULL DEFAULT ''",
)


def default_store_path() -> Path:
    override = os.environ.get("MYRM_DEV_GATE_DB", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-dev-gate/coordinator.sqlite3"


class DevGateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_store_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            for statement in _MIGRATIONS:
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError:
                    pass
        self.path.chmod(0o600)

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        session_id: str,
        version: int,
        event_type: str,
        state: SessionState,
        detail: dict[str, object],
        now: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events(
                session_id, version, event_type, state, created_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                version,
                event_type,
                state.value,
                now,
                json.dumps(detail, separators=(",", ":"), sort_keys=True),
            ),
        )

    def submit(
        self,
        *,
        session_id: str,
        owner_pid: int,
        owner_token: str,
        owner_process_start: str = "",
        owner_boot_id: str = "",
        test_node_id: str,
        policy: SessionPolicy,
        hard_deadline: float,
        now: float | None = None,
    ) -> SessionRecord:
        policy.validate()
        if not session_id.strip() or owner_pid <= 0 or not owner_token.strip():
            raise ValueError("session_id, owner_pid, and owner_token are required")
        created_at = time.time() if now is None else now
        state = initial_state(policy)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if existing is not None:
                record = self._record(existing)
                if (
                    record.owner_pid != owner_pid
                    or record.owner_token != owner_token
                    or record.owner_process_start != owner_process_start
                    or record.owner_boot_id != owner_boot_id
                    or record.test_node_id != test_node_id
                    or record.policy != policy
                ):
                    raise ValueError(f"session submit conflict: {session_id}")
                return record
            connection.execute(
                """
                INSERT INTO sessions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0, '',
                    '', '[]', '', '', '', '', '{}'
                )
                """,
                (
                    session_id,
                    owner_pid,
                    owner_token,
                    owner_process_start,
                    owner_boot_id,
                    test_node_id,
                    policy.execution_mode.value,
                    policy.access_scope.value,
                    policy.workload.value,
                    policy.namespace,
                    policy.priority,
                    policy.private_credits,
                    state.value,
                    created_at,
                    created_at,
                    created_at,
                    hard_deadline,
                ),
            )
            self._event(
                connection,
                session_id=session_id,
                version=1,
                event_type="SUBMIT",
                state=state,
                detail={},
                now=created_at,
            )
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError(f"session insert disappeared: {session_id}")
            return self._record(row)

    def transition(
        self,
        session_id: str,
        owner_token: str,
        target: SessionState,
        *,
        expected_version: int | None = None,
        current_node: str = "",
        failure_token: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        changed_at = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, session_id, owner_token)
            current = SessionState(row["state"])
            version = int(row["version"])
            if expected_version is not None and version != expected_version:
                raise ValueError(
                    f"session version conflict: expected={expected_version} actual={version}"
                )
            assert_transition(current, target)
            next_version = version + 1
            connection.execute(
                """
                UPDATE sessions
                SET state=?, version=?, phase_started_at=?, last_progress_at=?,
                    node_started_at=?, current_node=?, failure_token=?
                WHERE session_id=? AND version=?
                """,
                (
                    target.value,
                    next_version,
                    changed_at,
                    changed_at,
                    changed_at if current_node else float(row["node_started_at"]),
                    current_node or str(row["current_node"]),
                    failure_token,
                    session_id,
                    version,
                ),
            )
            self._event(
                connection,
                session_id=session_id,
                version=next_version,
                event_type="TRANSITION",
                state=target,
                detail={"from": current.value, "failure_token": failure_token},
                now=changed_at,
            )
            return self._record(
                self._required_row(connection, session_id)
            )

    def heartbeat(
        self,
        session_id: str,
        owner_token: str,
        *,
        current_node: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        touched_at = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            node_started = float(row["node_started_at"])
            if current_node and current_node != str(row["current_node"]):
                node_started = touched_at
            connection.execute(
                """
                UPDATE sessions SET version=?, last_progress_at=?,
                    node_started_at=?, current_node=?
                WHERE session_id=?
                """,
                (
                    version,
                    touched_at,
                    node_started,
                    current_node or str(row["current_node"]),
                    session_id,
                ),
            )
            return self._record(self._required_row(connection, session_id))

    def set_ownership(
        self,
        session_id: str,
        owner_token: str,
        ownership: SessionOwnership,
    ) -> SessionRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            connection.execute(
                """
                UPDATE sessions SET version=?, browser_context_id=?,
                    page_ids_json=?, lease_id=?, runtime_id=?
                WHERE session_id=?
                """,
                (
                    version,
                    ownership.browser_context_id,
                    json.dumps(ownership.page_ids, separators=(",", ":")),
                    ownership.lease_id,
                    ownership.runtime_id,
                    session_id,
                ),
            )
            return self._record(self._required_row(connection, session_id))

    def record_cleanup(
        self,
        session_id: str,
        owner_token: str,
        receipt: CleanupReceipt,
    ) -> SessionRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            connection.execute(
                "UPDATE sessions SET version=?, cleanup_json=? WHERE session_id=?",
                (
                    version,
                    json.dumps(
                        {
                            "closed_page_ids": receipt.closed_page_ids,
                            "closed_context_id": receipt.closed_context_id,
                            "released_lease_id": receipt.released_lease_id,
                            "released_runtime_id": receipt.released_runtime_id,
                            "ledger_cleaned": receipt.ledger_cleaned,
                            "completed_at": receipt.completed_at,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    session_id,
                ),
            )
            return self._record(self._required_row(connection, session_id))

    def finish(
        self,
        session_id: str,
        owner_token: str,
        *,
        succeeded: bool,
        failure_token: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        """Finalize a session from any nonterminal phase after best-effort teardown."""
        finished_at = time.time() if now is None else now
        target = SessionState.SUCCEEDED if succeeded else SessionState.FAILED
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, session_id, owner_token)
            current = SessionState(str(row["state"]))
            if current in {
                SessionState.SUCCEEDED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            }:
                return self._record(row)
            version = int(row["version"]) + 1
            outcome = "PASSED" if succeeded else "FAILED"
            connection.execute(
                """
                UPDATE sessions SET state=?, version=?, outcome=?,
                    failure_token=?, phase_started_at=?, last_progress_at=?
                WHERE session_id=?
                """,
                (
                    target.value,
                    version,
                    outcome,
                    failure_token,
                    finished_at,
                    finished_at,
                    session_id,
                ),
            )
            self._event(
                connection,
                session_id=session_id,
                version=version,
                event_type="FINISH",
                state=target,
                detail={"from": current.value, "outcome": outcome},
                now=finished_at,
            )
            return self._record(self._required_row(connection, session_id))

    def get(self, session_id: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return None if row is None else self._record(row)

    def list_active(self) -> tuple[SessionRecord, ...]:
        terminal = tuple(state.value for state in (
            SessionState.SUCCEEDED,
            SessionState.FAILED,
            SessionState.CANCELLED,
        ))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE state NOT IN (?, ?, ?)
                ORDER BY submitted_at, session_id
                """,
                terminal,
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def reap_abandoned(self, *, now: float | None = None) -> tuple[str, ...]:
        """Fail sessions whose owning process is gone and make cleanup auditable."""
        reaped_at = time.time() if now is None else now
        reaped: list[str] = []
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
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
                from owner_identity import owner_process_matches

                if owner_process_matches(pid=owner_pid, expected_start=owner_start):
                    continue
                session_id = str(row["session_id"])
                version = int(row["version"]) + 1
                cleanup = {
                    "closed_page_ids": [],
                    "closed_context_id": str(row["browser_context_id"]),
                    "released_lease_id": str(row["lease_id"]),
                    "released_runtime_id": str(row["runtime_id"]),
                    "ledger_cleaned": True,
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

    @staticmethod
    def _required_row(
        connection: sqlite3.Connection,
        session_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"session not found: {session_id}")
        return row

    def _owned_row(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        owner_token: str,
    ) -> sqlite3.Row:
        row = self._required_row(connection, session_id)
        if str(row["owner_token"]) != owner_token:
            raise PermissionError(f"session owner mismatch: {session_id}")
        return row

    @staticmethod
    def _record(row: sqlite3.Row) -> SessionRecord:
        pages_raw: object = json.loads(str(row["page_ids_json"]))
        page_ids = (
            tuple(str(item) for item in pages_raw)
            if isinstance(pages_raw, list)
            else ()
        )
        cleanup_raw: object = json.loads(str(row["cleanup_json"]))
        cleanup = cleanup_raw if isinstance(cleanup_raw, dict) else {}
        return SessionRecord(
            session_id=str(row["session_id"]),
            owner_pid=int(row["owner_pid"]),
            owner_token=str(row["owner_token"]),
            owner_process_start=str(row["owner_process_start"]),
            owner_boot_id=str(row["owner_boot_id"]),
            test_node_id=str(row["test_node_id"]),
            policy=SessionPolicy(
                execution_mode=ExecutionMode(str(row["execution_mode"])),
                access_scope=AccessScope(str(row["access_scope"])),
                workload=Workload(str(row["workload"])),
                namespace=str(row["namespace"]),
                priority=int(row["priority"]),
                private_credits=int(row["private_credits"]),
            ),
            state=SessionState(str(row["state"])),
            version=int(row["version"]),
            submitted_at=float(row["submitted_at"]),
            phase_started_at=float(row["phase_started_at"]),
            last_progress_at=float(row["last_progress_at"]),
            hard_deadline=float(row["hard_deadline"]),
            node_started_at=float(row["node_started_at"]),
            current_node=str(row["current_node"]),
            ownership=SessionOwnership(
                browser_context_id=str(row["browser_context_id"]),
                page_ids=page_ids,
                lease_id=str(row["lease_id"]),
                runtime_id=str(row["runtime_id"]),
            ),
            outcome=str(row["outcome"]),
            failure_token=str(row["failure_token"]),
            cleanup=CleanupReceipt(
                closed_page_ids=tuple(
                    str(item) for item in cleanup.get("closed_page_ids", ())
                ),
                closed_context_id=str(cleanup.get("closed_context_id", "")),
                released_lease_id=str(cleanup.get("released_lease_id", "")),
                released_runtime_id=str(cleanup.get("released_runtime_id", "")),
                ledger_cleaned=cleanup.get("ledger_cleaned") is True,
                completed_at=float(cleanup.get("completed_at", 0.0)),
            ),
        )
