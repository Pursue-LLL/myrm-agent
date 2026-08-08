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
    CleanupUnsealedError,
    ExecutionMode,
    SessionOwnership,
    SessionPolicy,
    SessionRecord,
    SessionState,
    TERMINAL_STATES,
    TerminalConflictError,
    Workload,
    assert_transition,
    initial_state,
)

from real_user_home import real_user_home


def _cleanup_dict_from_row(row: sqlite3.Row) -> dict[str, object]:
    try:
        cleanup = json.loads(str(row["cleanup_json"] or "{}"))
    except json.JSONDecodeError:
        cleanup = {}
    return cleanup if isinstance(cleanup, dict) else {}


def _require_cleanup_sealed_for_success(row: sqlite3.Row) -> None:
    cleanup = _cleanup_dict_from_row(row)
    if cleanup.get("sealed") is True:
        return
    session_id = str(row["session_id"])
    raise CleanupUnsealedError(
        f"cannot finish succeeded: cleanup not sealed for session {session_id}"
    )


def _normalize_cleanup_receipt(receipt: CleanupReceipt) -> CleanupReceipt:
    """Only observed seals are accepted; a sealed receipt without an observation
    timestamp is synthetic (fake green) and is downgraded to fail-closed."""
    if not receipt.sealed:
        return receipt
    if receipt.observed_at <= 0.0:
        return CleanupReceipt(
            closed_page_ids=receipt.closed_page_ids,
            closed_context_id=receipt.closed_context_id,
            released_lease_id=receipt.released_lease_id,
            released_runtime_id=receipt.released_runtime_id,
            ledger_cleaned=receipt.ledger_cleaned,
            physical_released=receipt.physical_released,
            sealed=False,
            requested_at=receipt.requested_at,
            observed_at=receipt.observed_at,
            completed_at=receipt.completed_at,
        )
    return receipt


def _cleanup_receipt_payload(receipt: CleanupReceipt) -> str:
    return json.dumps(
        {
            "closed_page_ids": receipt.closed_page_ids,
            "closed_context_id": receipt.closed_context_id,
            "released_lease_id": receipt.released_lease_id,
            "released_runtime_id": receipt.released_runtime_id,
            "ledger_cleaned": receipt.ledger_cleaned,
            "physical_released": receipt.physical_released,
            "sealed": receipt.sealed,
            "requested_at": receipt.requested_at,
            "observed_at": receipt.observed_at,
            "completed_at": receipt.completed_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _begin_immediate(connection: sqlite3.Connection) -> None:
    for attempt in range(20):
        try:
            connection.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= 19:
                raise
            time.sleep(min(0.05 * (2**attempt), 3.0))


DEFAULT_JOURNAL_RETENTION_SEC: float = 7 * 86400

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
    pytest_evidence_hash TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS ownership_resources (
    session_id TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource_value TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, resource_key)
);
CREATE INDEX IF NOT EXISTS ownership_resources_session_idx
ON ownership_resources(session_id, updated_at);
"""

_MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE sessions ADD COLUMN owner_process_start TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN owner_boot_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN pytest_evidence_hash TEXT NOT NULL DEFAULT ''",
)


def default_store_path() -> Path:
    override = os.environ.get("MYRM_DEV_GATE_DB", "").strip()
    if override:
        return Path(override).resolve()
    return real_user_home() / ".local/state/myrm-dev-gate/coordinator.sqlite3"


class OwnershipConflictError(RuntimeError):
    """Raised when an ownership CAS update loses against a newer session version."""


def _dev_gate_sqlite_busy_timeout_ms() -> int:
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


class DevGateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_store_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        busy_ms = _dev_gate_sqlite_busy_timeout_ms()
        connection.execute(f"PRAGMA busy_timeout={busy_ms}")
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
            _begin_immediate(connection)
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
                if record.state in TERMINAL_STATES:
                    # v2.1: detach retry reuses session_id — reset terminal rows.
                    version = record.version + 1
                    connection.execute(
                        """
                        UPDATE sessions SET
                            state=?,
                            version=?,
                            submitted_at=?,
                            phase_started_at=?,
                            last_progress_at=?,
                            hard_deadline=?,
                            node_started_at=0,
                            current_node='',
                            browser_context_id='',
                            page_ids_json='[]',
                            lease_id='',
                            runtime_id='',
                            outcome='',
                            failure_token='',
                            pytest_evidence_hash='',
                            cleanup_json='{}'
                        WHERE session_id=?
                        """,
                        (
                            state.value,
                            version,
                            created_at,
                            created_at,
                            created_at,
                            hard_deadline,
                            session_id,
                        ),
                    )
                    connection.execute(
                        "DELETE FROM private_admission WHERE session_id=?",
                        (session_id,),
                    )
                    self._event(
                        connection,
                        session_id=session_id,
                        version=version,
                        event_type="RESUBMIT",
                        state=state,
                        detail={"prior_state": record.state.value},
                        now=created_at,
                    )
                    row = connection.execute(
                        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
                    ).fetchone()
                    assert row is not None
                    return self._record(row)
                return record
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    owner_pid,
                    owner_token,
                    owner_process_start,
                    owner_boot_id,
                    test_node_id,
                    execution_mode,
                    access_scope,
                    workload,
                    namespace,
                    priority,
                    private_credits,
                    state,
                    version,
                    submitted_at,
                    phase_started_at,
                    last_progress_at,
                    hard_deadline,
                    node_started_at,
                    current_node,
                    browser_context_id,
                    page_ids_json,
                    lease_id,
                    runtime_id,
                    outcome,
                    failure_token,
                    cleanup_json
                ) VALUES (
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
            _begin_immediate(connection)
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
            return self._record(self._required_row(connection, session_id))

    def heartbeat(
        self,
        session_id: str,
        owner_token: str,
        *,
        current_node: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        last_locked: sqlite3.OperationalError | None = None
        for attempt in range(12):
            try:
                return self._heartbeat_once(
                    session_id,
                    owner_token,
                    current_node=current_node,
                    now=now,
                )
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_locked = exc
                time.sleep(min(0.2 * float(attempt + 1), 2.0))
        if last_locked is not None:
            raise last_locked
        raise RuntimeError("heartbeat retry exhausted without result")

    def _heartbeat_once(
        self,
        session_id: str,
        owner_token: str,
        *,
        current_node: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        touched_at = time.time() if now is None else now
        with self._connect() as connection:
            _begin_immediate(connection)
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
        *,
        expected_version: int | None = None,
    ) -> SessionRecord:
        touched_at = time.time()
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current_version = int(row["version"])
            if expected_version is not None and current_version != expected_version:
                raise OwnershipConflictError(
                    f"ownership version mismatch: session={session_id} "
                    f"expected={expected_version} actual={current_version}"
                )
            version = current_version + 1
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
            self._sync_ownership_resource_rows(
                connection,
                session_id=session_id,
                ownership=ownership,
                version=version,
                updated_at=touched_at,
            )
            return self._record(self._required_row(connection, session_id))

    def cas_add_page_id(
        self,
        session_id: str,
        owner_token: str,
        page_id: str,
        *,
        expected_version: int,
    ) -> SessionRecord:
        """Merge one page id under session-version CAS (P0-D resource-key row)."""
        normalized = page_id.strip()
        if not normalized:
            raise ValueError("page_id must be non-empty")
        touched_at = time.time()
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current_version = int(row["version"])
            if current_version != expected_version:
                raise OwnershipConflictError(
                    f"ownership version mismatch: session={session_id} "
                    f"expected={expected_version} actual={current_version}"
                )
            pages_raw = self._load_json_field(row["page_ids_json"], default=[])
            page_ids = (
                tuple(str(item) for item in pages_raw)
                if isinstance(pages_raw, list)
                else ()
            )
            if normalized in page_ids:
                return self._record(row)
            merged = page_ids + (normalized,)
            version = current_version + 1
            connection.execute(
                """
                UPDATE sessions SET version=?, page_ids_json=?
                WHERE session_id=?
                """,
                (
                    version,
                    json.dumps(merged, separators=(",", ":")),
                    session_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO ownership_resources(
                    session_id, resource_key, resource_kind, resource_value,
                    version, updated_at
                ) VALUES (?, ?, 'page', ?, ?, ?)
                ON CONFLICT(session_id, resource_key) DO UPDATE SET
                    resource_value=excluded.resource_value,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                WHERE excluded.version >= ownership_resources.version
                """,
                (
                    session_id,
                    f"page:{normalized}",
                    normalized,
                    version,
                    touched_at,
                ),
            )
            return self._record(self._required_row(connection, session_id))

    @staticmethod
    def _sync_ownership_resource_rows(
        connection: sqlite3.Connection,
        *,
        session_id: str,
        ownership: SessionOwnership,
        version: int,
        updated_at: float,
    ) -> None:
        rows: list[tuple[str, str, str, str]] = []
        if ownership.browser_context_id:
            rows.append(
                (
                    "browser_context",
                    "browser_context",
                    ownership.browser_context_id,
                )
            )
        if ownership.lease_id:
            rows.append(("lease", "lease", ownership.lease_id))
        if ownership.runtime_id:
            rows.append(("runtime", "runtime", ownership.runtime_id))
        for page_id in ownership.page_ids:
            normalized = page_id.strip()
            if normalized:
                rows.append((f"page:{normalized}", "page", normalized))
        for resource_key, resource_kind, resource_value in rows:
            connection.execute(
                """
                INSERT INTO ownership_resources(
                    session_id, resource_key, resource_kind, resource_value,
                    version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, resource_key) DO UPDATE SET
                    resource_value=excluded.resource_value,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                WHERE excluded.version >= ownership_resources.version
                """,
                (
                    session_id,
                    resource_key,
                    resource_kind,
                    resource_value,
                    version,
                    updated_at,
                ),
            )

    def destroy_ownership(
        self,
        session_id: str,
        owner_token: str,
    ) -> SessionRecord:
        """P0-A destroy: clear keyed ownership in one transaction.

        Physical page/context destroy is performed by the pytest process; this
        ledger-side destroy makes the ownership_cleared seal check observably true.
        """
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            pages_raw = DevGateStore._load_json_field(row["page_ids_json"], default=[])
            closed_pages = (
                tuple(str(item) for item in pages_raw)
                if isinstance(pages_raw, list)
                else ()
            )
            closed_context = str(row["browser_context_id"])
            self._clear_session_ownership(connection, session_id=session_id)
            connection.execute(
                "UPDATE sessions SET version=? WHERE session_id=?",
                (version, session_id),
            )
            self._event(
                connection,
                session_id=session_id,
                version=version,
                event_type="DESTROY_SESSION",
                state=SessionState(str(row["state"])),
                detail={
                    "closed_page_ids": closed_pages,
                    "closed_context_id": closed_context,
                },
                now=time.time(),
            )
            return self._record(self._required_row(connection, session_id))

    def record_cleanup(
        self,
        session_id: str,
        owner_token: str,
        receipt: CleanupReceipt,
    ) -> SessionRecord:
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            final_receipt = _normalize_cleanup_receipt(receipt)
            if final_receipt.sealed:
                self._clear_session_ownership(connection, session_id=session_id)
            connection.execute(
                "UPDATE sessions SET version=?, cleanup_json=? WHERE session_id=?",
                (version, _cleanup_receipt_payload(final_receipt), session_id),
            )
            return self._record(self._required_row(connection, session_id))

    def teardown_and_finish(
        self,
        session_id: str,
        owner_token: str,
        receipt: CleanupReceipt,
        *,
        succeeded: bool,
        failure_token: str = "",
        pytest_evidence_hash: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        """Atomically persist cleanup receipt and terminal state (P0-A)."""
        last_locked: sqlite3.OperationalError | None = None
        for attempt in range(8):
            try:
                return self._teardown_and_finish_once(
                    session_id,
                    owner_token,
                    receipt,
                    succeeded=succeeded,
                    failure_token=failure_token,
                    pytest_evidence_hash=pytest_evidence_hash,
                    now=now,
                )
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_locked = exc
                time.sleep(min(0.2 * float(attempt + 1), 2.0))
        if last_locked is not None:
            raise last_locked
        raise RuntimeError("teardown_and_finish retry exhausted without result")

    def _teardown_and_finish_once(
        self,
        session_id: str,
        owner_token: str,
        receipt: CleanupReceipt,
        *,
        succeeded: bool,
        failure_token: str = "",
        pytest_evidence_hash: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        finished_at = time.time() if now is None else now
        target = SessionState.SUCCEEDED if succeeded else SessionState.FAILED
        terminal_only = False
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current = SessionState(str(row["state"]))
            if current in TERMINAL_STATES:
                terminal_only = True
            else:
                final_receipt = _normalize_cleanup_receipt(receipt)
                if succeeded and not final_receipt.sealed:
                    raise CleanupUnsealedError(
                        "cannot finish succeeded: cleanup not sealed "
                        f"for session {session_id}"
                    )
                if final_receipt.sealed:
                    self._clear_session_ownership(connection, session_id=session_id)
                version = int(row["version"]) + 1
                outcome = "PASSED" if succeeded else "FAILED"
                connection.execute(
                    """
                    UPDATE sessions SET state=?, version=?, outcome=?,
                        failure_token=?, pytest_evidence_hash=?, cleanup_json=?,
                        phase_started_at=?, last_progress_at=?
                    WHERE session_id=?
                    """,
                    (
                        target.value,
                        version,
                        outcome,
                        failure_token,
                        pytest_evidence_hash,
                        _cleanup_receipt_payload(final_receipt),
                        finished_at,
                        finished_at,
                        session_id,
                    ),
                )
                self._event(
                    connection,
                    session_id=session_id,
                    version=version,
                    event_type="TEARDOWN_FINISH",
                    state=target,
                    detail={
                        "from": current.value,
                        "outcome": outcome,
                        "cleanup_sealed": final_receipt.sealed,
                        "pytest_evidence_hash": pytest_evidence_hash,
                    },
                    now=finished_at,
                )
                return self._record(self._required_row(connection, session_id))
        if terminal_only:
            return self._finish_once(
                session_id,
                owner_token,
                succeeded=succeeded,
                failure_token=failure_token,
                pytest_evidence_hash=pytest_evidence_hash,
                now=now,
            )
        raise RuntimeError("teardown_and_finish reached unreachable path")

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

    def finish(
        self,
        session_id: str,
        owner_token: str,
        *,
        succeeded: bool,
        failure_token: str = "",
        pytest_evidence_hash: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        """Finalize a session from any nonterminal phase after best-effort teardown."""
        last_locked: sqlite3.OperationalError | None = None
        for attempt in range(8):
            try:
                return self._finish_once(
                    session_id,
                    owner_token,
                    succeeded=succeeded,
                    failure_token=failure_token,
                    pytest_evidence_hash=pytest_evidence_hash,
                    now=now,
                )
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_locked = exc
                time.sleep(min(0.2 * float(attempt + 1), 2.0))
        if last_locked is not None:
            raise last_locked
        raise RuntimeError("finish retry exhausted without result")

    def _finish_once(
        self,
        session_id: str,
        owner_token: str,
        *,
        succeeded: bool,
        failure_token: str = "",
        pytest_evidence_hash: str = "",
        now: float | None = None,
    ) -> SessionRecord:
        finished_at = time.time() if now is None else now
        target = SessionState.SUCCEEDED if succeeded else SessionState.FAILED
        with self._connect() as connection:
            _begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current = SessionState(str(row["state"]))
            if current in TERMINAL_STATES:
                if succeeded and current is SessionState.FAILED:
                    prior_token = str(row["failure_token"] or "")
                    cleanup = _cleanup_dict_from_row(row)
                    if prior_token == "OWNER_EXITED" and cleanup.get("sealed") is True:
                        version = int(row["version"]) + 1
                        connection.execute(
                            """
                            UPDATE sessions SET state=?, version=?, outcome=?,
                                failure_token='', pytest_evidence_hash=?,
                                phase_started_at=?, last_progress_at=?
                            WHERE session_id=?
                            """,
                            (
                                SessionState.SUCCEEDED.value,
                                version,
                                "PASSED",
                                pytest_evidence_hash,
                                finished_at,
                                finished_at,
                                session_id,
                            ),
                        )
                        self._event(
                            connection,
                            session_id=session_id,
                            version=version,
                            event_type="FINISH_OWNER_EXITED_RECOVERY",
                            state=SessionState.SUCCEEDED,
                            detail={
                                "prior_failure_token": prior_token,
                                "pytest_evidence_hash": pytest_evidence_hash,
                            },
                            now=finished_at,
                        )
                        return self._record(self._required_row(connection, session_id))
                if succeeded and current is not SessionState.SUCCEEDED:
                    raise TerminalConflictError(
                        f"cannot finish succeeded: session already {current.value}"
                    )
                if not succeeded and current is SessionState.SUCCEEDED:
                    raise TerminalConflictError(
                        f"cannot finish failed: session already {current.value}"
                    )
                return self._record(row)
            if succeeded:
                _require_cleanup_sealed_for_success(row)
            version = int(row["version"]) + 1
            outcome = "PASSED" if succeeded else "FAILED"
            connection.execute(
                """
                UPDATE sessions SET state=?, version=?, outcome=?,
                    failure_token=?, pytest_evidence_hash=?, phase_started_at=?,
                    last_progress_at=?
                WHERE session_id=?
                """,
                (
                    target.value,
                    version,
                    outcome,
                    failure_token,
                    pytest_evidence_hash,
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
                detail={
                    "from": current.value,
                    "outcome": outcome,
                    "pytest_evidence_hash": pytest_evidence_hash,
                },
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
        terminal = tuple(
            state.value
            for state in (
                SessionState.SUCCEEDED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            )
        )
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
            _begin_immediate(connection)
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
            _begin_immediate(connection)
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

    def latest_event_id(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(event_id), 0) AS max_id
                FROM events WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
        return 0 if row is None else int(row["max_id"])

    def fetch_events_after(
        self,
        session_id: str,
        *,
        after_event_id: int,
        event_types: frozenset[str] | None = None,
    ) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            if event_types:
                placeholders = ",".join("?" for _ in event_types)
                rows = connection.execute(
                    f"""
                    SELECT event_id, event_type, state, created_at, detail_json, version
                    FROM events
                    WHERE session_id=? AND event_id>? AND event_type IN ({placeholders})
                    ORDER BY event_id ASC
                    """,
                    (session_id, after_event_id, *sorted(event_types)),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_id, event_type, state, created_at, detail_json, version
                    FROM events
                    WHERE session_id=? AND event_id>?
                    ORDER BY event_id ASC
                    """,
                    (session_id, after_event_id),
                ).fetchall()
        events: list[dict[str, object]] = []
        for row in rows:
            detail_raw = self._load_json_field(row["detail_json"], default={})
            detail = detail_raw if isinstance(detail_raw, dict) else {}
            events.append(
                {
                    "event_id": int(row["event_id"]),
                    "event_type": str(row["event_type"]),
                    "state": str(row["state"]),
                    "created_at": float(row["created_at"]),
                    "version": int(row["version"]),
                    "detail": detail,
                }
            )
        return tuple(events)

    def list_recent_sessions(self, *, limit: int = 200) -> tuple[SessionRecord, ...]:
        bounded = max(1, min(int(limit), 2000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                ORDER BY submitted_at DESC, session_id DESC
                LIMIT ?
                """,
                (bounded,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def fetch_recent_events(
        self,
        *,
        limit: int = 2000,
        session_ids: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, object], ...]:
        bounded = max(1, min(int(limit), 10000))
        with self._connect() as connection:
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                rows = connection.execute(
                    f"""
                    SELECT event_id, session_id, event_type, state, created_at,
                           detail_json, version
                    FROM events
                    WHERE session_id IN ({placeholders})
                    ORDER BY event_id DESC
                    LIMIT ?
                    """,
                    (*session_ids, bounded),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_id, session_id, event_type, state, created_at,
                           detail_json, version
                    FROM events
                    ORDER BY event_id DESC
                    LIMIT ?
                    """,
                    (bounded,),
                ).fetchall()
        events: list[dict[str, object]] = []
        for row in reversed(rows):
            detail_raw = self._load_json_field(row["detail_json"], default={})
            detail = detail_raw if isinstance(detail_raw, dict) else {}
            events.append(
                {
                    "event_id": int(row["event_id"]),
                    "session_id": str(row["session_id"]),
                    "event_type": str(row["event_type"]),
                    "state": str(row["state"]),
                    "created_at": float(row["created_at"]),
                    "version": int(row["version"]),
                    "detail": detail,
                }
            )
        return tuple(events)

    def list_ownership_resources(
        self,
        *,
        session_ids: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                rows = connection.execute(
                    f"""
                    SELECT session_id, resource_key, resource_kind, resource_value,
                           version, updated_at
                    FROM ownership_resources
                    WHERE session_id IN ({placeholders})
                    ORDER BY session_id, resource_key
                    """,
                    session_ids,
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT session_id, resource_key, resource_kind, resource_value,
                           version, updated_at
                    FROM ownership_resources
                    ORDER BY session_id, resource_key
                    """
                ).fetchall()
        return tuple(
            {
                "session_id": str(row["session_id"]),
                "resource_key": str(row["resource_key"]),
                "resource_kind": str(row["resource_kind"]),
                "resource_value": str(row["resource_value"]),
                "version": int(row["version"]),
                "updated_at": float(row["updated_at"]),
            }
            for row in rows
        )

    def journal_stats(self) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS event_count,
                       MIN(created_at) AS oldest_at,
                       MAX(created_at) AS newest_at
                FROM events
                """
            ).fetchone()
        if row is None:
            return {"event_count": 0, "oldest_at": None, "newest_at": None}
        oldest = row["oldest_at"]
        newest = row["newest_at"]
        return {
            "event_count": int(row["event_count"]),
            "oldest_at": None if oldest is None else float(oldest),
            "newest_at": None if newest is None else float(newest),
            "retention_sec": DEFAULT_JOURNAL_RETENTION_SEC,
        }

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
        pages_raw = DevGateStore._load_json_field(row["page_ids_json"], default=[])
        page_ids = (
            tuple(str(item) for item in pages_raw)
            if isinstance(pages_raw, list)
            else ()
        )
        cleanup_raw = DevGateStore._load_json_field(row["cleanup_json"], default={})
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
                sealed=cleanup.get("sealed") is True,
                requested_at=float(cleanup.get("requested_at", 0.0)),
                observed_at=float(cleanup.get("observed_at", 0.0)),
                completed_at=float(cleanup.get("completed_at", 0.0)),
            ),
        )
