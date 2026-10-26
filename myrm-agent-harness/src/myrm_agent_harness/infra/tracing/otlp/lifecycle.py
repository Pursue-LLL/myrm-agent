"""Bounded provider flush and shutdown.

[INPUT]
- (none: standard library only)

[OUTPUT]
- run_bounded: run a blocking provider action with a deadline

[POS]
A hung collector must never hold up a request or process exit. The action runs on a daemon thread
and the caller waits at most ``timeout_ms``; a late thread is detached, not joined.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


def run_bounded(action: Callable[[], object], *, thread_name: str, timeout_ms: float, label: str) -> bool:
    """Run ``action`` on a daemon thread; False when it timed out or raised."""
    errors: list[Exception] = []

    def _worker() -> None:
        try:
            action()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_worker, name=thread_name, daemon=True)
    thread.start()
    thread.join(timeout=max(0.01, timeout_ms / 1000.0))
    if thread.is_alive():
        logger.warning("%s timed out after %.1fms (daemon thread detached)", label, timeout_ms)
        return False
    if errors:
        logger.error("Error during %s: %s", label, errors[0])
        return False
    return True
