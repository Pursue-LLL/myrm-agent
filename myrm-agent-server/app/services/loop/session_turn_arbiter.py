"""Session Turn Arbiter — mediates priority between user input and loop wakeups.

[INPUT]
- Chat ID and turn event triggers (user input submitted vs loop timer fired)

[OUTPUT]
- Concurrency arbitration decision: user input always preempts loop wakeups,
  granting immediate lock ownership and deferring loop tick.

[POS]
Server service layer. Protects against 409 session lock conflicts and interleaving turn bugs.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class SessionTurnArbiter:
    """Singleton arbiter enforcing user-first concurrency policy for active loops."""

    _instance: SessionTurnArbiter | None = None

    def __init__(self) -> None:
        # Track timestamp of last user interaction per chat to defer wakeups
        self._last_user_activity: dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> SessionTurnArbiter:
        """Access global arbiter instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record_user_activity(self, chat_id: str) -> None:
        """Mark recent user activity on chat to prevent immediate loop wakeup collision."""
        self._last_user_activity[chat_id] = time.time()

    def should_defer_loop_wakeup(self, chat_id: str, *, grace_period_seconds: float = 3.0) -> bool:
        """Check if recent user activity warrants deferring loop wakeup."""
        last_active = self._last_user_activity.get(chat_id, 0.0)
        return (time.time() - last_active) < grace_period_seconds

    def clean_chat(self, chat_id: str) -> None:
        """Evict tracked chat upon loop completion or chat deletion."""
        self._last_user_activity.pop(chat_id, None)
