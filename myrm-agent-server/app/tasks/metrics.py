"""Prometheus instruments for the task queue and its SSE event bus, plus the recorders that update them.

[INPUT]
- myrm_agent_harness.observability.metrics::{create_counter, create_histogram} (POS: Harness-layer generic metrics utilities for any project using the Myrm framework)

[OUTPUT]
- task_succeeded_total / task_failed_total / task_cancelled_total / task_timeout_total: task outcome counters
- task_duration_seconds: execution duration histogram by task type and final status
- task_event_emitted_total / task_event_dropped_total / task_event_replaced_total: SSE event delivery counters
- safe_counter_inc / safe_histogram_observe: record one sample and never raise into the caller

[POS]
- Prometheus instruments and best-effort recorders for the task subsystem. The worker and the event bus record through the
  safe_* recorders, so a telemetry fault (a label set that drifted from its declaration, or an absent client) cannot fail a
  task settlement or evict a healthy SSE subscriber. Declare an instrument only together with the code that writes it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.observability.metrics import create_counter, create_histogram

if TYPE_CHECKING:
    from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Task counters
task_succeeded_total = create_counter(
    "task_succeeded_total",
    "Total number of tasks succeeded",
    ("task_type",),
)

task_failed_total = create_counter(
    "task_failed_total",
    "Total number of tasks failed",
    ("task_type", "error_type"),
)

task_cancelled_total = create_counter(
    "task_cancelled_total",
    "Total number of tasks cancelled",
    ("task_type",),
)

task_timeout_total = create_counter(
    "task_timeout_total",
    "Total number of tasks timed out",
    ("task_type",),
)

# Task event bus counters
task_event_emitted_total = create_counter(
    "task_event_emitted_total",
    "Total number of task events emitted to subscribers",
    ("status",),
)

task_event_dropped_total = create_counter(
    "task_event_dropped_total",
    "Total number of task events dropped due to subscriber backpressure",
    ("status", "reason"),
)

task_event_replaced_total = create_counter(
    "task_event_replaced_total",
    "Total number of task events delivered by replacing oldest buffered event",
    ("status",),
)

# Task duration
task_duration_seconds = create_histogram(
    "task_duration_seconds",
    "Task execution duration in seconds",
    ("task_type", "status"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)


def safe_counter_inc(counter: Counter, **labels: str) -> None:
    """Increment *counter* (its *labels* child when given); a telemetry fault is logged at debug level, never raised.

    The harness factories return ``None`` when prometheus_client is absent and a label set that drifted from its
    declaration raises ``ValueError``; neither may fail the settlement or delivery being measured.
    """
    try:
        (counter.labels(**labels) if labels else counter).inc()
    except Exception as exc:
        logger.debug("Failed to record a task counter (labels=%s): %s", labels, exc)


def safe_histogram_observe(histogram: Histogram, value: float, **labels: str) -> None:
    """Observe *value* on *histogram* (its *labels* child when given) under the same never-raise contract."""
    try:
        (histogram.labels(**labels) if labels else histogram).observe(value)
    except Exception as exc:
        logger.debug("Failed to record a task histogram sample (labels=%s): %s", labels, exc)


__all__ = [
    "safe_counter_inc",
    "safe_histogram_observe",
    "task_cancelled_total",
    "task_duration_seconds",
    "task_event_dropped_total",
    "task_event_emitted_total",
    "task_event_replaced_total",
    "task_failed_total",
    "task_succeeded_total",
    "task_timeout_total",
]
