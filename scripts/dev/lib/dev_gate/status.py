"""Registry-first observability for Chrome E2E shared and private execution."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing

from desktop_seat_controller import desktop_seat_capacity
from dev_gate_session import ExecutionMode, SessionState
from dev_gate_store import DevGateStore, default_store_path
from private_resource_controller import (
    PrivateResourceController,
    private_capacity_credits,
)


def _unavailable_registry_status(*, registry_error: str = "") -> dict[str, object]:
    capacity = private_capacity_credits()
    payload: dict[str, object] = {
        "shared_unlimited": True,
        "shared_active": 0,
        "private_active": 0,
        "private_waiting": 0,
        "private_active_credits": 0,
        "private_capacity_credits": capacity,
        "private_available_credits": capacity,
        "private_credit_idle_reason": "unknown",
        "desktop_active_seats": 0,
        "desktop_waiting": 0,
        "desktop_capacity_seats": desktop_seat_capacity(),
        "sessions": [],
        "reaped_session_ids": [],
        "registry_observability": "unknown",
    }
    if registry_error:
        payload["registry_error"] = registry_error
    return payload


def _dev_gate_status_once() -> dict[str, object]:
    database = default_store_path()
    if not database.is_file():
        return _unavailable_registry_status()
    try:
        connection = sqlite3.connect(
            f"{database.as_uri()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=2000")
    except (OSError, PermissionError, sqlite3.OperationalError):
        return _unavailable_registry_status()
    with closing(connection), connection:
        terminal = tuple(
            state.value
            for state in (
                SessionState.SUCCEEDED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            )
        )
        session_rows = connection.execute(
            """
            SELECT * FROM sessions
            WHERE state NOT IN (?, ?, ?)
            ORDER BY submitted_at, session_id
            """,
            terminal,
        ).fetchall()
        sessions = tuple(DevGateStore._record(row) for row in session_rows)
        capacity = private_capacity_credits()
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        private_active_credits = 0
        waiting: list[sqlite3.Row] = []
        if "private_admission" in tables:
            private_active_row = connection.execute(
                """
                SELECT COALESCE(SUM(credits), 0) AS total
                FROM private_admission
                WHERE granted_at IS NOT NULL AND released_at IS NULL
                """
            ).fetchone()
            private_active_credits = (
                int(private_active_row["total"])
                if private_active_row is not None
                else 0
            )
            now = time.time()
            waiting = list(
                connection.execute(
                    """
                    SELECT session_id, credits, priority, enqueued_at
                    FROM private_admission
                    WHERE granted_at IS NULL AND released_at IS NULL
                    ORDER BY priority + CAST((? - enqueued_at) / 60 AS INTEGER) DESC,
                        enqueued_at, session_id
                    """,
                    (now,),
                ).fetchall()
            )
        desktop_active = 0
        desktop_waiting: list[sqlite3.Row] = []
        if "desktop_seat_admission" in tables:
            desktop_active_row = connection.execute(
                """
                SELECT COUNT(*) AS total FROM desktop_seat_admission
                WHERE granted_at IS NOT NULL AND released_at IS NULL
                """
            ).fetchone()
            desktop_active = (
                int(desktop_active_row["total"])
                if desktop_active_row is not None
                else 0
            )
            desktop_waiting = list(
                connection.execute(
                    """
                    SELECT session_id, enqueued_at FROM desktop_seat_admission
                    WHERE granted_at IS NULL AND released_at IS NULL
                    ORDER BY enqueued_at, session_id
                    """
                ).fetchall()
            )
    private_available = max(0, capacity - private_active_credits)
    private_idle_reason = PrivateResourceController._credit_idle_reason(
        active_credits=private_active_credits,
        available_credits=private_available,
        waiting_rows=list(waiting),
    )
    shared_active = sum(
        record.policy.execution_mode is ExecutionMode.SHARED for record in sessions
    )
    private_active = sum(
        record.policy.execution_mode is ExecutionMode.PRIVATE
        and record.state is not SessionState.PRIVATE_ADMIT
        for record in sessions
    )
    return {
        "shared_unlimited": True,
        "shared_active": shared_active,
        "private_active": private_active,
        "private_waiting": len(waiting),
        "private_active_credits": private_active_credits,
        "private_capacity_credits": capacity,
        "private_available_credits": private_available,
        "private_credit_idle_reason": private_idle_reason,
        "desktop_active_seats": desktop_active,
        "desktop_waiting": len(desktop_waiting),
        "desktop_capacity_seats": desktop_seat_capacity(),
        "sessions": [record.to_dict() for record in sessions],
        "reaped_session_ids": [],
        "registry_observability": "ok",
    }


def dev_gate_status() -> dict[str, object]:
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(12):
        try:
            return _dev_gate_status_once()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            last_error = exc
            if attempt >= 11:
                break
            time.sleep(min(0.25 * (2**attempt), 2.0))
    error_text = str(last_error) if last_error is not None else "database_locked"
    return _unavailable_registry_status(registry_error=error_text)
