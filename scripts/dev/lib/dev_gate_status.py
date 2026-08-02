"""Registry-first observability for Chrome E2E shared and private execution."""

from __future__ import annotations

import sqlite3
import time

from dev_gate_session import ExecutionMode, SessionState
from dev_gate_store import DevGateStore, default_store_path
from private_resource_controller import (
    PrivateResourceController,
    private_capacity_credits,
)
from desktop_seat_controller import DesktopSeatController, desktop_seat_capacity


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
        store = DevGateStore(database)
    except (OSError, PermissionError):
        return _unavailable_registry_status()
    sessions = store.list_active()
    controller = PrivateResourceController(
        store,
        capacity_credits=capacity,
    )
    private = controller.snapshot()
    desktop_controller = DesktopSeatController(
        store,
        capacity_seats=desktop_seat_capacity(),
    )
    desktop = desktop_controller.snapshot()
    waiting_raw = private.get("waiting", [])
    waiting = waiting_raw if isinstance(waiting_raw, list) else []
    shared_active = sum(
        record.policy.execution_mode is ExecutionMode.SHARED for record in sessions
    )
    private_active = sum(
        record.policy.execution_mode is ExecutionMode.PRIVATE
        and record.state is not SessionState.PRIVATE_ADMIT
        for record in sessions
    )
    desktop_waiting_raw = desktop.get("waiting", [])
    desktop_waiting = (
        desktop_waiting_raw if isinstance(desktop_waiting_raw, list) else []
    )
    return {
        "shared_unlimited": True,
        "shared_active": shared_active,
        "private_active": private_active,
        "private_waiting": len(waiting),
        "private_active_credits": int(private.get("active_credits", 0)),
        "private_capacity_credits": int(private.get("capacity_credits", 0)),
        "private_available_credits": int(private.get("available_credits", 0)),
        "private_credit_idle_reason": str(private.get("idle_reason", "unknown")),
        "desktop_active_seats": int(desktop.get("active_seats", 0)),
        "desktop_waiting": len(desktop_waiting),
        "desktop_capacity_seats": int(desktop.get("capacity_seats", 0)),
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
