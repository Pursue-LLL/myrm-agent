"""Journal-backed session event wait helpers (P0-D event subscription foundation)."""

from __future__ import annotations

import time

from dev_gate.store import DevGateStore


class SessionEventTimeoutError(TimeoutError):
    """Raised when no matching coordinator journal event arrives within budget."""


def wait_for_session_event(
    store: DevGateStore,
    *,
    session_id: str,
    event_types: frozenset[str],
    after_event_id: int = 0,
    budget_sec: float = 30.0,
    poll_sec: float = 0.25,
) -> dict[str, object]:
    """Block until a matching journal event appears (journal subscription stub)."""
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
        time.sleep(min(max(0.05, poll_sec), remaining))
    raise SessionEventTimeoutError(
        f"session event wait timed out: session={session_id} "
        f"types={sorted(event_types)} budget_sec={budget_sec}"
    )
