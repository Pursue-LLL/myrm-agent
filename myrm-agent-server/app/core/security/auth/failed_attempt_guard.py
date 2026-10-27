"""
[INPUT]
- (stdlib only)

[OUTPUT]
- FailedAttemptGuard: per-key failed-attempt counter with a lockout window and a bounded key set

[POS]
Brute-force throttle for credential checks that cannot rely on a verified identity (WebUI login, share passwords).
Callers check ``retry_after`` before verifying a credential, ``record_failure`` on a wrong one and ``clear`` on success.
State is in-process and lost on restart; the key set is bounded because callers may derive keys from unauthenticated input.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable


class FailedAttemptGuard:
    """Locks a key for the rest of its window once it has accumulated ``max_failures`` failures."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 60.0,
        max_keys: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_failures < 1 or window_seconds <= 0 or max_keys < 1:
            raise ValueError("max_failures and max_keys must be >= 1 and window_seconds must be > 0")
        self._max_failures = max_failures
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._failures: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Seconds until *key* may try again, or ``None`` when it is not locked."""
        with self._lock:
            now = self._clock()
            recent = self._recent(key, now)
            if not recent:
                self._failures.pop(key, None)
                return None
            if len(recent) < self._max_failures:
                return None
            return max(1, int(self._window - (now - recent[0])))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            recent = self._recent(key, now)
            recent.append(now)
            self._failures.pop(key, None)
            self._failures[key] = recent[-self._max_failures :]
            while len(self._failures) > self._max_keys:
                self._failures.popitem(last=False)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _recent(self, key: str, now: float) -> list[float]:
        return [ts for ts in self._failures.get(key, ()) if now - ts < self._window]
