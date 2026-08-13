"""In-process session event subscription hub for coordinator waiters (P0-D)."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_gate.store import DevGateStore

_WRITE_OPERATIONS = frozenset(
    {
        "submit",
        "transition",
        "heartbeat",
        "ownership",
        "cleanup",
        "finish",
        "private_admit",
        "private_release",
        "desktop_admit",
        "desktop_release",
        "reap",
    }
)


class SessionEventHub:
    """Session-scoped condition variables; wake waiters after durable writes."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._conditions: dict[str, threading.Condition] = {}

    def notify(self, session_id: str) -> None:
        if not session_id:
            return
        with self._guard:
            condition = self._conditions.get(session_id)
        if condition is None:
            return
        with condition:
            condition.notify_all()

    def wait(self, session_id: str, *, timeout_sec: float) -> None:
        bounded = max(0.0, timeout_sec)
        if bounded <= 0:
            return
        with self._guard:
            condition = self._conditions.setdefault(
                session_id,
                threading.Condition(self._guard),
            )
        with condition:
            condition.wait(timeout=bounded)


_HUB: SessionEventHub | None = None


def coordinator_event_hub() -> SessionEventHub:
    global _HUB
    if _HUB is None:
        _HUB = SessionEventHub()
    return _HUB


def reset_coordinator_event_hub() -> None:
    global _HUB
    _HUB = None


def notify_write_result(
    request: dict[str, object],
    result: dict[str, object],
) -> None:
    """Wake session waiters after a coordinator mutation commits."""
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in _WRITE_OPERATIONS:
        return
    hub = coordinator_event_hub()
    session_ids: set[str] = set()
    session_raw = request.get("session_id")
    if isinstance(session_raw, str) and session_raw.strip():
        session_ids.add(session_raw.strip())
    if operation in {"private_admit", "private_release"}:
        granted = result.get("granted_session_ids")
        if isinstance(granted, list):
            for item in granted:
                if isinstance(item, str) and item.strip():
                    session_ids.add(item.strip())
    elif operation in {"desktop_admit", "desktop_release"}:
        granted = result.get("granted_session_ids")
        if isinstance(granted, list):
            for item in granted:
                if isinstance(item, str) and item.strip():
                    session_ids.add(item.strip())
    elif operation == "reap":
        reaped = result.get("reaped_session_ids")
        if isinstance(reaped, list):
            for item in reaped:
                if isinstance(item, str) and item.strip():
                    session_ids.add(item.strip())
    elif operation == "submit":
        session = result.get("session")
        if isinstance(session, dict):
            sid = session.get("session_id")
            if isinstance(sid, str) and sid.strip():
                session_ids.add(sid.strip())
    else:
        session = result.get("session")
        if isinstance(session, dict):
            sid = session.get("session_id")
            if isinstance(sid, str) and sid.strip():
                session_ids.add(sid.strip())
    for session_id in session_ids:
        hub.notify(session_id)


def wait_for_session_event_subscribed(
    store: DevGateStore,
    hub: SessionEventHub,
    *,
    session_id: str,
    event_types: frozenset[str],
    after_event_id: int = 0,
    budget_sec: float = 30.0,
) -> dict[str, object]:
    """Block on hub wake + journal read; avoids fixed-interval SQLite polling."""
    if not event_types:
        raise ValueError("event_types must be non-empty")
    deadline = time.monotonic() + max(0.1, budget_sec)
    cursor = after_event_id
    while time.monotonic() < deadline:
        events = store.fetch_events_after(
            session_id,
            after_event_id=cursor,
            event_types=event_types,
        )
        if events:
            return events[-1]
        cursor = store.latest_event_id(session_id)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        hub.wait(session_id, timeout_sec=remaining)
    from dev_gate.event_wait import SessionEventTimeoutError

    raise SessionEventTimeoutError(
        f"session event wait timed out: session={session_id} "
        f"types={sorted(event_types)} budget_sec={budget_sec}"
    )
