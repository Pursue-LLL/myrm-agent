"""Prometheus metrics for task monitoring.

Uses Harness layer metrics utilities for consistent naming (myrm_ prefix).
"""

from myrm_agent_harness.observability.metrics import (
    create_counter,
    create_gauge,
    create_histogram,
)

# Task counters
task_created_total = create_counter(
    "task_created_total",
    "Total number of tasks created",
    ("task_type",),
)

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

task_cache_hit_total = create_counter(
    "task_cache_hit_total",
    "Total number of task cache hits",
    ("task_type",),
)

task_retry_total = create_counter(
    "task_retry_total",
    "Total number of task retries",
    ("task_type",),
)

# Task duration
task_duration_seconds = create_histogram(
    "task_duration_seconds",
    "Task execution duration in seconds",
    ("task_type", "status"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)

# Task queue gauge
task_queue_length = create_gauge(
    "task_queue_length",
    "Number of tasks in queue",
    ("status",),
)

# Worker health
worker_active_count = create_gauge(
    "worker_active_count",
    "Number of active workers",
    (),
)

worker_heartbeat_timestamp = create_gauge(
    "worker_heartbeat_timestamp",
    "Last worker heartbeat timestamp",
    ("worker_id",),
)

__all__ = [
    "task_created_total",
    "task_succeeded_total",
    "task_failed_total",
    "task_cancelled_total",
    "task_timeout_total",
    "task_cache_hit_total",
    "task_retry_total",
    "task_duration_seconds",
    "task_queue_length",
    "worker_active_count",
    "worker_heartbeat_timestamp",
]
