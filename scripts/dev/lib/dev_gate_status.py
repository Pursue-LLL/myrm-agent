"""Registry-first observability for Chrome E2E shared and private execution."""

from __future__ import annotations

from dev_gate_session import ExecutionMode, SessionState
from dev_gate_store import DevGateStore, default_store_path
from private_resource_controller import (
    PrivateResourceController,
    private_capacity_credits,
)
from desktop_seat_controller import DesktopSeatController, desktop_seat_capacity


def dev_gate_status() -> dict[str, object]:
    database = default_store_path()
    capacity = private_capacity_credits()
    unavailable: dict[str, object] = {
        "shared_unlimited": True,
        "shared_active": 0,
        "private_active": 0,
        "private_waiting": 0,
        "private_active_credits": 0,
        "private_capacity_credits": capacity,
        "desktop_active_seats": 0,
        "desktop_waiting": 0,
        "desktop_capacity_seats": desktop_seat_capacity(),
        "sessions": [],
        "reaped_session_ids": [],
    }
    if not database.is_file():
        return unavailable
    try:
        store = DevGateStore(database)
    except (OSError, PermissionError):
        return unavailable
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
        "desktop_active_seats": int(desktop.get("active_seats", 0)),
        "desktop_waiting": len(desktop_waiting),
        "desktop_capacity_seats": int(desktop.get("capacity_seats", 0)),
        "sessions": [record.to_dict() for record in sessions],
        "reaped_session_ids": [],
    }
