"""Domain-level learning data shared by web_fetch and the browser.

[INPUT]
- web_fetch.fetchers.protocols::FetcherType (POS: Fetch tier identifiers)

[OUTPUT]
- DomainMetrics: Per-domain fetch failures and browser wait-strategy learning data
- PersistedMetrics: JSON shape of a stored DomainMetrics
- domain_key: Key under which a URL's domain is tracked

[POS]
Data model of the per-domain learning store; persistence and maintenance live in domain_metrics.py.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Required, TypedDict
from urllib.parse import urlparse

from ..fetchers.protocols import FetcherType

# SMART wait tuning trusts a domain's networkidle history only from this many samples on.
_SMART_MIN_SAMPLES = 20
_SMART_MIN_SUCCESS_RATE = 0.5
_MAX_FAILURE_SAMPLES = 100
_MAX_WAIT_SAMPLES = 200


class PersistedMetrics(TypedDict, total=False):
    """JSON shape of a stored ``DomainMetrics``; keys it does not list are ignored when loading."""

    domain: Required[str]
    wait_strategy_latencies: dict[str, list[float]]
    networkidle_success_count: int
    networkidle_fail_count: int
    failure_timestamps: dict[str, list[float]]
    last_access: float


def domain_key(url: str) -> str:
    """Key under which the domain of ``url`` is tracked.

    The lower-cased host with its port; a URL without a host is its own key.
    """
    try:
        return urlparse(url).netloc.lower() or url.lower()
    except ValueError:
        return url.lower()


@dataclass
class DomainMetrics:
    """Unified domain learning metrics

    Responsibility: aggregate domain-level learning data from web_fetch and browser

    Core data:
    - wait_strategy_latencies: Per-wait-strategy latency history (domain-level)
    - networkidle_success_count: networkidle Success count
    - networkidle_fail_count: networkidle Failure count
    - failure_timestamps: Per-fetcher failure timestamps (for time decay)
    - last_access: Last time anything was recorded (inactive domains are cleaned up by it)

    Persistence is the job of ``DomainMetricsManager`` (``domain_metrics.py``).

    Concurrency safety:
    - Internally uses threading.Lock to protect all mutations
    """

    domain: str
    wait_strategy_latencies: dict[str, deque[float]] = field(default_factory=dict)
    networkidle_success_count: int = 0
    networkidle_fail_count: int = 0
    failure_timestamps: dict[FetcherType, deque[float]] = field(default_factory=dict)
    last_access: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Seed one failure queue per fetcher type"""
        for ft in FetcherType:
            self.failure_timestamps.setdefault(ft, deque(maxlen=_MAX_FAILURE_SAMPLES))

    def __getstate__(self) -> dict[str, object]:
        """Custom serialization (excludes lock objects)"""
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict[str, object]) -> None:
        """Custom deserialization (rebuilds lock objects)"""
        self.__dict__.update(state)
        self._lock = threading.Lock()

    def to_dict(self) -> PersistedMetrics:
        """Serialize to JSON-storable dict"""
        return {
            "domain": self.domain,
            "wait_strategy_latencies": {strategy: list(dq) for strategy, dq in self.wait_strategy_latencies.items()},
            "networkidle_success_count": self.networkidle_success_count,
            "networkidle_fail_count": self.networkidle_fail_count,
            "failure_timestamps": {ft.name: list(dq) for ft, dq in self.failure_timestamps.items()},
            "last_access": self.last_access,
        }

    @classmethod
    def from_dict(cls, data: PersistedMetrics) -> DomainMetrics:
        """Deserialize from dict (keys it does not know are ignored)"""
        metrics = cls(domain=data["domain"])
        metrics.wait_strategy_latencies = {
            strategy: deque(latencies, maxlen=_MAX_WAIT_SAMPLES)
            for strategy, latencies in data.get("wait_strategy_latencies", {}).items()
        }
        metrics.networkidle_success_count = data.get("networkidle_success_count", 0)
        metrics.networkidle_fail_count = data.get("networkidle_fail_count", 0)
        for ft_name, timestamps in data.get("failure_timestamps", {}).items():
            metrics.failure_timestamps[FetcherType[ft_name]] = deque(timestamps, maxlen=_MAX_FAILURE_SAMPLES)
        metrics.last_access = data.get("last_access", time.time())
        return metrics

    def record_failure(self, fetcher_type: FetcherType) -> None:
        """Record a failed fetch attempt of a tier (thread-safe)"""
        with self._lock:
            now = time.time()
            self.failure_timestamps[fetcher_type].append(now)
            self.last_access = now

    def record_wait_strategy(self, strategy: str, elapsed_ms: int) -> None:
        """Record wait strategy latency (thread-safe)"""
        with self._lock:
            self.last_access = time.time()
            if strategy not in self.wait_strategy_latencies:
                self.wait_strategy_latencies[strategy] = deque(maxlen=_MAX_WAIT_SAMPLES)
            self.wait_strategy_latencies[strategy].append(float(elapsed_ms))

    def record_networkidle_result(self, success: bool) -> None:
        """Record networkidle detection result (thread-safe)"""
        with self._lock:
            self.last_access = time.time()
            if success:
                self.networkidle_success_count += 1
            else:
                self.networkidle_fail_count += 1

    def get_recent_failures_count(self, fetcher_type: FetcherType, window_hours: int = 24) -> int:
        """Get failure count within time window (time-decayed, thread-safe)"""
        with self._lock:
            now = time.time()
            cutoff = now - window_hours * 3600
            return sum(1 for ts in self.failure_timestamps[fetcher_type] if ts >= cutoff)

    def _networkidle_unreliable_locked(self) -> bool:
        """Whether enough samples show networkidle rarely settles here (caller holds ``_lock``)."""
        total = self.networkidle_success_count + self.networkidle_fail_count
        return total >= _SMART_MIN_SAMPLES and self.networkidle_success_count / total < _SMART_MIN_SUCCESS_RATE

    def should_skip_smart_fast_path(self) -> bool:
        """Whether SMART waits should go straight to the hybrid probe for this domain (thread-safe)

        Only a measured pattern justifies it: at least 20 networkidle samples with a success rate
        below 50%. Missing data is no evidence, so the default fast path applies instead.
        """
        with self._lock:
            return self._networkidle_unreliable_locked()

    def get_smart_fast_timeout(self) -> int | None:
        """Compute SMART strategy fast_timeout_ms from historical data (thread-safe)

        ``None`` means "nothing learned, use the default timeout". It never means "skip the fast
        path": that decision is ``should_skip_smart_fast_path``.

        Strategy:
        - Sample count < 20, or networkidle success rate < 50%: return None
        - Fewer than 20 recorded networkidle latencies: return None
        - Otherwise return P95 latency * 1.2 (capped at 500ms)
        """
        with self._lock:
            total = self.networkidle_success_count + self.networkidle_fail_count
            if total < _SMART_MIN_SAMPLES or self._networkidle_unreliable_locked():
                return None

            latencies = self.wait_strategy_latencies.get("networkidle")
            if not latencies or len(latencies) < _SMART_MIN_SAMPLES:
                return None

            sorted_latencies = sorted(latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p95_latency = sorted_latencies[p95_idx]

            return min(int(p95_latency * 1.2), 500)
