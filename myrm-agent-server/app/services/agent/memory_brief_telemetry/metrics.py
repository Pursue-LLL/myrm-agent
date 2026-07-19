"""@input: (none — optional prometheus_client)
@output: MEMORY_STATUS_* Counter/Gauge handles for memory brief telemetry
@pos: Prometheus metric definitions for memory brief status telemetry (graceful no-op when client absent).
"""

from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge
except Exception:  # pragma: no cover - optional dependency in some runtimes
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]

if Counter is not None:
    MEMORY_STATUS_DROPPED = Counter(
        "myrm_memory_brief_status_telemetry_dropped_total",
        "Memory brief status telemetry events dropped due to queue backpressure.",
        labelnames=("telemetry_subject", "dropped_phase", "incoming_phase"),
    )
    MEMORY_STATUS_FLUSH_EXCEPTIONS = Counter(
        "myrm_memory_brief_status_telemetry_flush_exceptions_total",
        "Unexpected flush-loop exceptions in memory brief status telemetry dispatcher.",
        labelnames=("telemetry_subject",),
    )
    MEMORY_STATUS_FLUSH_HTTP_ERRORS = Counter(
        "myrm_memory_brief_status_telemetry_flush_http_errors_total",
        "HTTP flush failures for memory brief status telemetry dispatcher after retries.",
        labelnames=("telemetry_subject",),
    )
    MEMORY_STATUS_FLUSH_ATTEMPTS = Counter(
        "myrm_memory_brief_status_telemetry_flush_attempts_total",
        "HTTP flush attempts for memory brief status telemetry dispatcher.",
        labelnames=("telemetry_subject",),
    )
else:  # pragma: no cover - optional dependency in some runtimes
    MEMORY_STATUS_DROPPED = None
    MEMORY_STATUS_FLUSH_EXCEPTIONS = None
    MEMORY_STATUS_FLUSH_HTTP_ERRORS = None
    MEMORY_STATUS_FLUSH_ATTEMPTS = None

if Gauge is not None:
    MEMORY_STATUS_QUEUE_DEPTH = Gauge(
        "myrm_memory_brief_status_telemetry_queue_depth",
        "Current queue depth for memory brief status telemetry dispatcher.",
        labelnames=("telemetry_subject",),
    )
    MEMORY_STATUS_QUEUE_FILL_RATIO = Gauge(
        "myrm_memory_brief_status_telemetry_queue_fill_ratio",
        "Current queue fill ratio (0-1) for memory brief status telemetry dispatcher.",
        labelnames=("telemetry_subject",),
    )
else:  # pragma: no cover - optional dependency in some runtimes
    MEMORY_STATUS_QUEUE_DEPTH = None
    MEMORY_STATUS_QUEUE_FILL_RATIO = None
