"""Per-session L4 fetch attempt counter (session cap enforcement).

[INPUT]

[OUTPUT]
- SessionEscalationCounter: Thread-safe counter keyed by agent session id.
- session_escalation_counter: Module-level singleton instance.

[POS]
Per-session L4 fetch attempt counter enforcing session-level escalation caps.
"""

from __future__ import annotations

import threading


class SessionEscalationCounter:
    """Thread-safe counter keyed by agent session id."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def try_acquire(self, session_id: str, cap: int) -> bool:
        if cap <= 0:
            return False
        with self._lock:
            current = self._counts.get(session_id, 0)
            if current >= cap:
                return False
            self._counts[session_id] = current + 1
            return True

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._counts.pop(session_id, None)


session_escalation_counter = SessionEscalationCounter()
