"""Route metrics protocol for observability and monitoring.

Provides framework-agnostic metrics collection for channel routes,
enabling QPS, latency, error rate monitoring.

[INPUT]

[OUTPUT]
- RouteMetricsProtocol: Framework-agnostic metrics interface
- NoOpMetrics: No-op implementation (default)
- InMemoryMetrics: In-memory metrics aggregation

[POS]
Protocol layer for route observability. Enables business layer to
choose appropriate metrics backend (Prometheus, Datadog, in-memory).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RouteMetricsProtocol(Protocol):
    """Protocol for collecting route performance metrics.

    Implementations can use different backends (no-op, in-memory, Prometheus, Datadog)
    based on deployment requirements.
    """

    def record_request(
        self,
        route_path: str,
        method: str,
        status_code: int,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        """Record a single request metrics.

        Args:
            route_path: Full route path
            method: HTTP method
            status_code: HTTP status code
            latency_ms: Request latency in milliseconds
            error: Optional error message (if request failed)
        """
        ...

    def get_qps(self, route_path: str, window_seconds: int = 60) -> float:
        """Get queries per second for a route.

        Args:
            route_path: Full route path
            window_seconds: Time window for QPS calculation

        Returns:
            QPS value
        """
        ...

    def get_error_rate(self, route_path: str, window_seconds: int = 60) -> float:
        """Get error rate (4xx/5xx) for a route.

        Args:
            route_path: Full route path
            window_seconds: Time window for error rate calculation

        Returns:
            Error rate (0.0-1.0)
        """
        ...

    def get_avg_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """Get average latency for a route.

        Args:
            route_path: Full route path
            window_seconds: Time window for latency calculation

        Returns:
            Average latency in milliseconds
        """
        ...

    def get_p99_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """Get p99 latency for a route.

        Args:
            route_path: Full route path
            window_seconds: Time window for latency calculation

        Returns:
            P99 latency in milliseconds
        """
        ...


class NoOpMetrics:
    """No-op metrics collector.

    Default implementation for Agent-in-Sandbox environments where
    detailed metrics collection is unnecessary.
    """

    def record_request(
        self,
        route_path: str,
        method: str,
        status_code: int,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        """No-op implementation."""
        pass

    def get_qps(self, route_path: str, window_seconds: int = 60) -> float:
        """No-op implementation."""
        return -1.0

    def get_error_rate(self, route_path: str, window_seconds: int = 60) -> float:
        """No-op implementation."""
        return -1.0

    def get_avg_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """No-op implementation."""
        return -1.0

    def get_p99_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """No-op implementation."""
        return -1.0


class InMemoryMetrics:
    """In-memory metrics collector with sliding window.

    Collects and aggregates request metrics in memory for single-instance
    sandbox environments. NOT suitable for distributed deployments.
    """

    def __init__(self, max_samples: int = 10000) -> None:
        """Initialize metrics collector.

        Args:
            max_samples: Maximum number of samples to keep per route (FIFO)
        """
        self._max_samples = max_samples
        self._samples: dict[str, list[tuple[float, int, float, str | None]]] = defaultdict(list)

    def record_request(
        self,
        route_path: str,
        method: str,
        status_code: int,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        """Record a single request metrics.

        Stores (timestamp, status_code, latency_ms, error) tuple.
        """
        now = time.time()
        samples = self._samples[route_path]
        samples.append((now, status_code, latency_ms, error))

        if len(samples) > self._max_samples:
            samples.pop(0)

    def get_qps(self, route_path: str, window_seconds: int = 60) -> float:
        """Get queries per second for a route."""
        samples = self._samples.get(route_path, [])
        if not samples:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds
        recent = [s for s in samples if s[0] >= cutoff]

        return len(recent) / window_seconds if recent else 0.0

    def get_error_rate(self, route_path: str, window_seconds: int = 60) -> float:
        """Get error rate (4xx/5xx) for a route."""
        samples = self._samples.get(route_path, [])
        if not samples:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds
        recent = [s for s in samples if s[0] >= cutoff]

        if not recent:
            return 0.0

        error_count = sum(1 for s in recent if s[1] >= 400)
        return error_count / len(recent)

    def get_avg_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """Get average latency for a route."""
        samples = self._samples.get(route_path, [])
        if not samples:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds
        recent = [s for s in samples if s[0] >= cutoff]

        if not recent:
            return 0.0

        return sum(s[2] for s in recent) / len(recent)

    def get_p99_latency(self, route_path: str, window_seconds: int = 60) -> float:
        """Get p99 latency for a route."""
        samples = self._samples.get(route_path, [])
        if not samples:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds
        recent = [s for s in samples if s[0] >= cutoff]

        if not recent:
            return 0.0

        latencies = sorted([s[2] for s in recent])
        p99_idx = int(len(latencies) * 0.99)
        return latencies[p99_idx] if p99_idx < len(latencies) else latencies[-1]

    def get_summary(self, route_path: str, window_seconds: int = 60) -> dict[str, float]:
        """Get comprehensive metrics summary for a route.

        Returns:
            Dictionary with qps, error_rate, avg_latency, p99_latency
        """
        return {
            "qps": self.get_qps(route_path, window_seconds),
            "error_rate": self.get_error_rate(route_path, window_seconds),
            "avg_latency_ms": self.get_avg_latency(route_path, window_seconds),
            "p99_latency_ms": self.get_p99_latency(route_path, window_seconds),
        }

    def reset(self, route_path: str | None = None) -> None:
        """Reset metrics for testing.

        Args:
            route_path: Optional route path to reset (resets all if None)
        """
        if route_path is None:
            self._samples.clear()
        elif route_path in self._samples:
            del self._samples[route_path]
