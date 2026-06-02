"""Slack thread tracker for auto-reply functionality.

[INPUT]
- (none)

[OUTPUT]
- ThreadTrackerMetrics: Metrics for ThreadTracker.
- ThreadTracker: Tracks Slack threads where the bot has participated.

[POS]
Slack thread tracker for auto-reply functionality.
"""

from __future__ import annotations

import collections
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class ThreadTrackerMetrics:
    """Metrics for ThreadTracker."""

    hit_count: int = 0
    miss_count: int = 0
    current_size: int = 0

    def get_hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class ThreadTracker:
    """Tracks Slack threads where the bot has participated.

    Uses an LRU cache to store thread_ts.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, bool] = collections.OrderedDict()
        self.metrics = ThreadTrackerMetrics()

    def add(self, thread_ts: str) -> None:
        """Add a thread_ts to the tracker."""
        if thread_ts in self._cache:
            self._cache.move_to_end(thread_ts)
        else:
            self._cache[thread_ts] = True
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
            self.metrics.current_size = len(self._cache)

    def contains(self, thread_ts: str) -> bool:
        """Check if a thread_ts is in the tracker."""
        if thread_ts in self._cache:
            self._cache.move_to_end(thread_ts)
            self.metrics.hit_count += 1
            return True
        self.metrics.miss_count += 1
        return False
