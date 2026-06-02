"""Channel metrics data structures for observability.

[INPUT]

[OUTPUT]
- ChannelMetrics: per-channel performance metrics dataclass
- MetricPoint: single metric sample with timestamp

[POS]
Framework-level metrics data layer. Provides structured data only;
business layer (myrm-agent-server) decides monitoring solution
(Prometheus, logs, DB, etc.). Aligns with resource_report.json design.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class MetricPoint:
    """Single metric sample with timestamp.

    Lightweight structure for time-series data collection.
    """

    value: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChannelMetrics:
    """Per-channel performance and health metrics.

    Framework provides data; business layer consumes via to_dict().
    All metrics are instance-level (reset on channel restart).

    Example:
        metrics = channel.metrics
        metrics.record_message()
        metrics.record_error()
        data = metrics.to_dict()
        # business layer decides: log, Prometheus, DB, etc.
    """

    message_count: int = 0
    error_count: int = 0
    rate_limit_hits: int = 0
    dlq_retry_success_count: int = 0
    _response_times: list[float] = field(default_factory=list, repr=False)
    _created_at: float = field(default_factory=time.time, repr=False)

    def record_message(self) -> None:
        """Increment inbound message counter."""
        self.message_count += 1

    def record_error(self) -> None:
        """Increment error counter."""
        self.error_count += 1

    def record_rate_limit_hit(self) -> None:
        """Increment rate limit counter."""
        self.rate_limit_hits += 1

    def record_dlq_retry_success(self) -> None:
        """Increment DLQ retry success counter."""
        self.dlq_retry_success_count += 1

    def record_response_time(self, ms: float) -> None:
        """Record response time sample (milliseconds).

        Keeps last 1000 samples for moving average calculation.
        """
        if len(self._response_times) >= 1000:
            self._response_times.pop(0)
        self._response_times.append(ms)

    def avg_response_ms(self) -> float:
        """Calculate average response time from recorded samples."""
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)

    def uptime_seconds(self) -> float:
        """Time elapsed since metrics creation (seconds)."""
        return time.time() - self._created_at

    def to_dict(self) -> dict[str, float]:
        """Export metrics as flat dictionary for external consumption.

        Business layer can serialize to JSON, push to Prometheus, etc.
        """
        return {
            "message_count": float(self.message_count),
            "error_count": float(self.error_count),
            "rate_limit_hits": float(self.rate_limit_hits),
            "dlq_retry_success_count": float(self.dlq_retry_success_count),
            "avg_response_ms": self.avg_response_ms(),
            "uptime_seconds": self.uptime_seconds(),
        }

    def reset(self) -> None:
        """Clear all metrics (useful for testing or manual reset)."""
        self.message_count = 0
        self.error_count = 0
        self.rate_limit_hits = 0
        self.dlq_retry_success_count = 0
        self._response_times.clear()
        self._created_at = time.time()
