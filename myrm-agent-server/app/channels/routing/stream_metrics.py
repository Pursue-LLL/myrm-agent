"""Streaming quality metrics collection and monitoring.

Tracks streaming performance indicators:
- Edit count and frequency
- Edit failures and recovery
- First-edit latency (TTFB)
- Chunk sizes and distribution
- Transmission efficiency (bytes saved by incremental editing)
- API latency percentiles (P50/P95/P99)
- Anomaly detection and alerting

[INPUT]
- infra.tracing.metrics::MetricsCollector (POS: Aggregates evolution metrics across all skills for system-level insights.)

[OUTPUT]
- StreamMetrics: Streaming quality metrics collector with production observability

[POS]
Provides observability into streaming quality via tracing infrastructure.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StreamingSession:
    """Metrics for a single streaming session."""

    session_key: str
    trace_id: str = ""
    start_time: float = field(default_factory=time.monotonic)
    first_edit_at: float = 0.0
    last_edit_at: float = 0.0
    edit_count: int = 0
    edit_failures: int = 0
    final_text_length: int = 0
    last_text_length: int = 0
    chunk_sizes: list[int] = field(default_factory=list)
    transmitted_bytes: int = 0
    total_bytes: int = 0
    api_latencies: list[float] = field(default_factory=list)
    decision_reasons: list[str] = field(default_factory=list)


class StreamMetrics:
    """Collects and reports streaming quality metrics.

    Metrics tracked:
    - stream.first_edit_latency_ms: Time to first edit (TTFB)
    - stream.edit_count: Total edits per session
    - stream.edit_failure_rate: Percentage of failed edits
    - stream.avg_chunk_size: Average chunk size
    - stream.total_chars: Total characters streamed
    - stream.transmission_efficiency: Bytes saved by incremental editing (0.0-1.0)
    - stream.api_latency_p50/p95/p99: API latency percentiles (ms)
    - Anomaly alerts when thresholds exceeded
    """

    def __init__(
        self,
        alert_callback: Callable[[str], None] | None = None,
        failure_threshold: float = 0.3,
        p95_latency_threshold: float = 2000.0,
    ) -> None:
        self._sessions: dict[str, StreamingSession] = {}
        self._alert_callback = alert_callback
        self._failure_threshold = failure_threshold
        self._p95_latency_threshold = p95_latency_threshold

    def start_session(self, session_key: str, trace_id: str = "") -> None:
        """Start tracking a new streaming session.

        Args:
            session_key: Unique session identifier
            trace_id: Optional trace ID for distributed tracing
        """
        self._sessions[session_key] = StreamingSession(session_key=session_key, trace_id=trace_id)

    def record_edit(
        self,
        session_key: str,
        text_length: int,
        success: bool,
        is_first: bool = False,
    ) -> None:
        """Record an edit attempt."""
        session = self._sessions.get(session_key)
        if not session:
            logger.debug("StreamMetrics: session %s not found", session_key)
            return

        now = time.monotonic()

        if is_first and session.first_edit_at == 0.0:
            session.first_edit_at = now

        if success:
            session.edit_count += 1
            session.last_edit_at = now
            session.final_text_length = text_length
            chunk_size = text_length - session.last_text_length
            if chunk_size > 0:
                session.chunk_sizes.append(chunk_size)
                session.last_text_length = text_length
        else:
            session.edit_failures += 1

    def record_transmission(
        self,
        session_key: str,
        transmitted_bytes: int,
        full_text_bytes: int,
    ) -> None:
        """Record transmission efficiency for incremental editing.

        Args:
            session_key: Unique session identifier
            transmitted_bytes: Bytes actually transmitted (after diff)
            full_text_bytes: Total bytes if sending full text
        """
        session = self._sessions.get(session_key)
        if not session:
            return

        session.transmitted_bytes += transmitted_bytes
        session.total_bytes += full_text_bytes

    def record_api_latency(self, session_key: str, latency_ms: float) -> None:
        """Record API call latency.

        Args:
            session_key: Unique session identifier
            latency_ms: API call latency in milliseconds
        """
        session = self._sessions.get(session_key)
        if not session:
            return

        session.api_latencies.append(latency_ms)

    def record_decision(self, session_key: str, reason: str) -> None:
        """Record streaming decision reason for debugging.

        Args:
            session_key: Unique session identifier
            reason: Decision reason from UpdateDecision
        """
        session = self._sessions.get(session_key)
        if not session:
            return

        session.decision_reasons.append(reason)

    def end_session(self, session_key: str) -> None:
        """End session and emit final metrics."""
        session = self._sessions.pop(session_key, None)
        if not session:
            return

        if session.edit_count + session.edit_failures > 0:
            failure_rate = session.edit_failures / (session.edit_count + session.edit_failures)
        else:
            failure_rate = 0.0

        p95_latency = 0.0
        if session.api_latencies:
            sorted_latencies = sorted(session.api_latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p95_latency = sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else sorted_latencies[-1]

        try:
            from myrm_agent_harness.infra.tracing.metrics import get_metrics_collector

            metrics = get_metrics_collector()
            labels = {"trace_id": session.trace_id} if session.trace_id else {}

            if session.first_edit_at > 0:
                first_edit_latency = (session.first_edit_at - session.start_time) * 1000
                metrics.histogram("stream.first_edit_latency_ms", first_edit_latency, labels)

            metrics.counter("stream.edit_count", session.edit_count, labels)

            if failure_rate > 0:
                metrics.gauge("stream.edit_failure_rate", failure_rate, labels)

            if session.chunk_sizes:
                avg_chunk = sum(session.chunk_sizes) / len(session.chunk_sizes)
                metrics.histogram("stream.avg_chunk_size", avg_chunk, labels)

            metrics.histogram("stream.total_chars", session.final_text_length, labels)

            duration_s = (session.last_edit_at - session.start_time) if session.last_edit_at > 0 else 0
            metrics.histogram("stream.session_duration_s", duration_s, labels)

            if session.total_bytes > 0:
                efficiency = 1.0 - (session.transmitted_bytes / session.total_bytes)
                metrics.gauge("stream.transmission_efficiency", efficiency, labels)

            if session.api_latencies:
                sorted_latencies = sorted(session.api_latencies)
                p50_idx = len(sorted_latencies) // 2
                p99_idx = int(len(sorted_latencies) * 0.99)

                p50 = sorted_latencies[p50_idx]
                p99 = sorted_latencies[p99_idx] if p99_idx < len(sorted_latencies) else sorted_latencies[-1]

                metrics.histogram("stream.api_latency_p50", p50, labels)
                metrics.histogram("stream.api_latency_p95", p95_latency, labels)
                metrics.histogram("stream.api_latency_p99", p99, labels)

            decision_summary = self._summarize_decisions(session.decision_reasons)
            trace_info = f" trace_id={session.trace_id}" if session.trace_id else ""

            logger.warning(
                "Stream session completed: edits=%d failures=%d chars=%d first_edit_ms=%.1f "
                "transmission_efficiency=%.1f%% p95_latency=%.1fms decisions=%s%s",
                session.edit_count,
                session.edit_failures,
                session.final_text_length,
                first_edit_latency if session.first_edit_at > 0 else 0,
                (1.0 - (session.transmitted_bytes / session.total_bytes)) * 100 if session.total_bytes > 0 else 0,
                p95_latency,
                decision_summary,
                trace_info,
            )

        except Exception as exc:
            logger.debug("Failed to emit stream metrics: %s", exc)

        if p95_latency > self._p95_latency_threshold:
            self._raise_alert(f"High P95 latency: {p95_latency:.1f}ms (threshold: {self._p95_latency_threshold}ms)")

        if failure_rate > self._failure_threshold:
            self._raise_alert(f"High failure rate: {failure_rate:.1%} (threshold: {self._failure_threshold:.1%})")

    def _summarize_decisions(self, reasons: list[str]) -> str:
        """Summarize decision reasons for logging.

        Args:
            reasons: List of decision reasons

        Returns:
            Summary string like "first_update(1) block_boundary(3) throttled(2)"
        """
        if not reasons:
            return "none"

        from collections import Counter

        counts = Counter(reasons)
        return " ".join(f"{reason}({count})" for reason, count in counts.most_common())

    def _raise_alert(self, message: str) -> None:
        """Raise an alert for anomaly detection."""
        logger.error("StreamMetrics ALERT: %s", message)
        if self._alert_callback:
            try:
                self._alert_callback(message)
            except Exception as exc:
                logger.debug("Alert callback failed: %s", exc)
