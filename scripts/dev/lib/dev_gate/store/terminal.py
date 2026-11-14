"""Terminal session states: cleanup receipts and the finish transitions."""

from __future__ import annotations

import json
import sqlite3
import time

from dev_gate.session import (
    TERMINAL_STATES,
    CleanupReceipt,
    CleanupUnsealedError,
    SessionRecord,
    SessionState,
    TerminalConflictError,
)
from dev_gate.store.base import StoreBase
from dev_gate.store.connection import begin_immediate


def _cleanup_dict_from_row(row: sqlite3.Row) -> dict[str, object]:
    try:
        cleanup = json.loads(str(row["cleanup_json"] or "{}"))
    except json.JSONDecodeError:
        cleanup = {}
    return cleanup if isinstance(cleanup, dict) else {}


def _require_cleanup_sealed_for_success(row: sqlite3.Row) -> None:
    cleanup = _cleanup_dict_from_row(row)
    observed_at = cleanup.get("observed_at")
    if (
        cleanup.get("sealed") is True
        and cleanup.get("ledger_cleaned") is True
        and cleanup.get("physical_released") is True
        and isinstance(observed_at, (int, float))
        and observed_at > 0.0
    ):
        return
    session_id = str(row["session_id"])
    raise CleanupUnsealedError(
        f"cannot finish succeeded: cleanup not sealed for session {session_id}"
    )


def _normalize_cleanup_receipt(receipt: CleanupReceipt) -> CleanupReceipt:
    """Accept a seal only when every cleanup observation is positive.

    A terminal session must carry both ledger and physical-release evidence.
    ``None`` is observability uncertainty, not success; allowing it to pass
    would turn an incomplete cleanup receipt into a false green.
    """
    if not receipt.sealed:
        return receipt
    if (
        receipt.observed_at <= 0.0
        or receipt.ledger_cleaned is not True
        or receipt.physical_released is not True
    ):
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


class TerminalMixin(StoreBase):
    """Operations that seal a session's cleanup and move it to a terminal state."""

    def record_cleanup(
        self,
        session_id: str,
        owner_token: str,
        receipt: CleanupReceipt,
    ) -> SessionRecord:
        with self._connect() as connection:
            begin_immediate(connection)
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
            begin_immediate(connection)
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
            begin_immediate(connection)
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
