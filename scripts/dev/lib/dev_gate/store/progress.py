"""Session intake and progress: submit, state transitions and heartbeats."""

from __future__ import annotations

import sqlite3
import time

from dev_gate.session import TERMINAL_STATES, SessionPolicy, SessionRecord, SessionState, assert_transition, initial_state
from dev_gate.store.base import StoreBase
from dev_gate.store.connection import begin_immediate


class ProgressMixin(StoreBase):
    """Operations that admit a session and move it through its running states."""

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
        meta: dict[str, str] | None = None,
        now: float | None = None,
    ) -> SessionRecord:
        policy.validate()
        if not session_id.strip() or owner_pid <= 0 or not owner_token.strip():
            raise ValueError("session_id, owner_pid, and owner_token are required")
        submit_meta = dict(meta or {})
        created_at = time.time() if now is None else now
        state = initial_state(policy)
        with self._connect() as connection:
            begin_immediate(connection)
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
                        detail={"prior_state": record.state.value, **submit_meta},
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
                detail=submit_meta,
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
            begin_immediate(connection)
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
            begin_immediate(connection)
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
