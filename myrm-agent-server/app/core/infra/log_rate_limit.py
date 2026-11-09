"""[INPUT]
- logging.LogRecord (POS: 待输出的日志记录)

[OUTPUT]
- LogStormFilter: 有界的重复日志限速过滤器

[POS]
日志风暴保护。后台循环每分钟可写出 GB 级日志并淹没根因；该过滤器保留首条、按
``(logger, level, 消息模板)`` 限速并有界记忆，下一条放行时附上被丢弃的数量。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Final

ENV_RATE_LIMIT: Final = "MYRM_LOG_RATE_LIMIT"
_DEFAULT_RATE_PER_SEC: Final = 200.0
_DEFAULT_BURST: Final = 400.0
_PER_KEY_RATE_PER_SEC: Final = 5.0
_PER_KEY_BURST: Final = 10.0
_ERROR_RATE_PER_SEC: Final = 50.0
_ERROR_BURST: Final = 100.0
_MAX_TRACKED_KEYS: Final = 1024
_SUMMARY_PREFIX: Final = "[+%d suppressed] "


def _configured_rate() -> float:
    """Read the optional override; a malformed value falls back to the default instead of failing startup."""
    raw = os.getenv(ENV_RATE_LIMIT)
    if not raw:
        return _DEFAULT_RATE_PER_SEC
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_RATE_PER_SEC


class _TokenBucket:
    """A monotonic token bucket; the clock is injectable so tests need no sleeping."""

    __slots__ = ("_tokens", "_updated", "_rate", "_burst")

    def __init__(self, rate: float, burst: float, now: float) -> None:
        self._tokens = burst
        self._updated = now
        self._rate = rate
        self._burst = burst

    def allow(self, now: float) -> bool:
        self._tokens = min(self._burst, self._tokens + (now - self._updated) * self._rate)
        self._updated = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True


class LogStormFilter(logging.Filter):
    """Keep log output bounded during a repeated-message storm.

    Two layers: a per-template bucket stops one message from flooding, and a process-wide bucket caps
    total output so many distinct messages cannot flood either. ``MYRM_LOG_RATE_LIMIT=0`` disables it.
    """

    def __init__(
        self,
        *,
        rate_per_sec: float | None = None,
        burst: float = _DEFAULT_BURST,
        max_tracked_keys: int = _MAX_TRACKED_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._rate = rate_per_sec if rate_per_sec is not None else _configured_rate()
        self._enabled = self._rate > 0
        self._burst = burst
        self._max_tracked_keys = max_tracked_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._global = _TokenBucket(self._rate, burst, clock())
        self._per_key: OrderedDict[tuple[str, int, str], _TokenBucket] = OrderedDict()
        self._suppressed: dict[tuple[str, int, str], int] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._enabled:
            return True

        now = self._clock()
        key = (record.name, record.levelno, record.msg if isinstance(record.msg, str) else "")
        with self._lock:
            bucket = self._per_key.get(key)
            first_error = bucket is None and record.levelno >= logging.ERROR
            if bucket is None:
                bucket = _TokenBucket(self._per_key_rate(record.levelno), self._per_key_burst(record.levelno), now)
                self._per_key[key] = bucket
                self._suppressed[key] = 0
                if len(self._per_key) > self._max_tracked_keys:
                    oldest, _ = self._per_key.popitem(last=False)
                    self._suppressed.pop(oldest, None)
            else:
                self._per_key.move_to_end(key)

            if first_error:
                # The first sighting of a distinct error must survive even a global flood.
                return True
            if not bucket.allow(now) or not self._global.allow(now):
                self._suppressed[key] = self._suppressed.get(key, 0) + 1
                return False

            dropped = self._suppressed.get(key, 0)
            if dropped and isinstance(record.msg, str):
                self._suppressed[key] = 0
                record.msg = (_SUMMARY_PREFIX % dropped) + record.msg
        return True

    @staticmethod
    def _per_key_rate(levelno: int) -> float:
        return _ERROR_RATE_PER_SEC if levelno >= logging.ERROR else _PER_KEY_RATE_PER_SEC

    @staticmethod
    def _per_key_burst(levelno: int) -> float:
        return _ERROR_BURST if levelno >= logging.ERROR else _PER_KEY_BURST
