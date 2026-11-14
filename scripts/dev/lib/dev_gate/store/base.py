"""Connection handling and row codecs that every Dev Gate store operation builds on."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dev_gate.session import (
    AccessScope,
    CleanupReceipt,
    ExecutionMode,
    SessionOwnership,
    SessionPolicy,
    SessionRecord,
    SessionState,
    Workload,
)
from dev_gate.store.connection import dev_gate_sqlite_busy_timeout_ms
from dev_gate.store.schema import MIGRATIONS, SCHEMA


class StoreBase:
    """Opens the database, creates the schema and converts rows; the operation mixins build on it."""

    path: Path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        busy_ms = dev_gate_sqlite_busy_timeout_ms()
        connection.execute(f"PRAGMA busy_timeout={busy_ms}")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            for statement in MIGRATIONS:
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

    @staticmethod
    def _clear_session_ownership(
        connection: sqlite3.Connection,
        *,
        session_id: str,
    ) -> None:
        connection.execute(
            """
            UPDATE sessions SET browser_context_id='', page_ids_json='[]',
                lease_id='', runtime_id=''
            WHERE session_id=?
            """,
            (session_id,),
        )
        connection.execute(
            "DELETE FROM ownership_resources WHERE session_id=?",
            (session_id,),
        )

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
    def _load_json_field(raw: object, *, default: object) -> object:
        text = str(raw or "").strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _record(row: sqlite3.Row) -> SessionRecord:
        pages_raw = StoreBase._load_json_field(row["page_ids_json"], default=[])
        page_ids = (
            tuple(str(item) for item in pages_raw)
            if isinstance(pages_raw, list)
            else ()
        )
        cleanup_raw = StoreBase._load_json_field(row["cleanup_json"], default={})
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
            pytest_evidence_hash=str(row["pytest_evidence_hash"]),
            cleanup=CleanupReceipt(
                closed_page_ids=tuple(
                    str(item) for item in cleanup.get("closed_page_ids", ())
                ),
                closed_context_id=str(cleanup.get("closed_context_id", "")),
                released_lease_id=str(cleanup.get("released_lease_id", "")),
                released_runtime_id=str(cleanup.get("released_runtime_id", "")),
                ledger_cleaned=cleanup.get("ledger_cleaned") is True,
                physical_released=(
                    True
                    if cleanup.get("physical_released") is True
                    else (
                        False
                        if cleanup.get("physical_released") is False
                        else None
                    )
                ),
                sealed=cleanup.get("sealed") is True,
                requested_at=float(cleanup.get("requested_at", 0.0)),
                observed_at=float(cleanup.get("observed_at", 0.0)),
                completed_at=float(cleanup.get("completed_at", 0.0)),
            ),
        )
