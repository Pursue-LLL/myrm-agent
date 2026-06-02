"""Business-layer example: Export Slack ThreadTracker metrics to monitoring systems.

This file demonstrates how to use ThreadTrackerMetrics from the framework layer
and export to various monitoring backends (Prometheus, DataDog, Logging).

Framework provides the data structure; business layer decides how to use it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from prometheus_client.registry import CollectorRegistry

    from app.channels.providers.slack import (
        SlackChannel,
    )


class _StatsdLike(Protocol):
    def gauge(self, metric: str, value: float, tags: list[str] | None = None) -> object: ...

logger = logging.getLogger(__name__)


def export_thread_metrics_to_prometheus(
    channel: SlackChannel,
    registry: CollectorRegistry | None,
    user_id: str | None = None,
) -> None:
    """Export thread tracker metrics to Prometheus.

    Args:
        channel: SlackChannel instance
        registry: Prometheus registry (pass prometheus_client.REGISTRY)
        user_id: Optional user ID for SaaS scenarios (multi-tenant label)

    Example:
        from prometheus_client import Gauge, REGISTRY

        # Create gauges
        thread_hit_rate = Gauge(
            'slack_thread_hit_rate',
            'Thread tracker cache hit rate',
            ['user_id'],
            registry=REGISTRY,
        )

        # Export metrics
        export_thread_metrics_to_prometheus(slack_channel, REGISTRY, user_id="user_123")
    """
    try:
        # Lazy import to avoid dependency in framework
        from prometheus_client import Gauge

    except ImportError:
        logger.warning("prometheus_client not installed, skipping Prometheus export")
        return

    metrics = channel.thread_tracker_metrics
    labels = {"user_id": user_id or "default"}

    # Define gauges (should be module-level singletons in production)
    gauges = {
        "hit_count": Gauge(
            "slack_thread_hit_count",
            "Thread tracker cache hits",
            ["user_id"],
            registry=registry,
        ),
        "miss_count": Gauge(
            "slack_thread_miss_count",
            "Thread tracker cache misses",
            ["user_id"],
            registry=registry,
        ),
        "current_size": Gauge(
            "slack_thread_current_size",
            "Thread tracker current size",
            ["user_id"],
            registry=registry,
        ),
        "lru_eviction_count": Gauge(
            "slack_thread_lru_eviction_count",
            "Thread tracker LRU evictions",
            ["user_id"],
            registry=registry,
        ),
        "ttl_eviction_count": Gauge(
            "slack_thread_ttl_eviction_count",
            "Thread tracker TTL evictions",
            ["user_id"],
            registry=registry,
        ),
        "hit_rate": Gauge(
            "slack_thread_hit_rate",
            "Thread tracker cache hit rate",
            ["user_id"],
            registry=registry,
        ),
    }

    # Set gauge values
    data = metrics.to_dict()
    gauges["hit_count"].labels(**labels).set(data["hit_count"])
    gauges["miss_count"].labels(**labels).set(data["miss_count"])
    gauges["current_size"].labels(**labels).set(data["current_size"])
    gauges["lru_eviction_count"].labels(**labels).set(data["lru_eviction_count"])
    gauges["ttl_eviction_count"].labels(**labels).set(data["ttl_eviction_count"])
    gauges["hit_rate"].labels(**labels).set(metrics.get_hit_rate())


def export_thread_metrics_to_datadog(
    channel: SlackChannel,
    statsd_client: _StatsdLike,
    user_id: str | None = None,
) -> None:
    """Export thread tracker metrics to DataDog.

    Args:
        channel: SlackChannel instance
        statsd_client: DataDog StatsD client
        user_id: Optional user ID for SaaS scenarios (multi-tenant tag)

    Example:
        from datadog import initialize, statsd

        initialize(statsd_host='127.0.0.1', statsd_port=8125)
        export_thread_metrics_to_datadog(slack_channel, statsd, user_id="user_123")
    """
    metrics = channel.thread_tracker_metrics
    tags = [f"user_id:{user_id or 'default'}"]

    # Send gauges
    data = metrics.to_dict()
    statsd_client.gauge("slack.thread.hit_count", data["hit_count"], tags=tags)
    statsd_client.gauge("slack.thread.miss_count", data["miss_count"], tags=tags)
    statsd_client.gauge("slack.thread.current_size", data["current_size"], tags=tags)
    statsd_client.gauge("slack.thread.lru_eviction_count", data["lru_eviction_count"], tags=tags)
    statsd_client.gauge("slack.thread.ttl_eviction_count", data["ttl_eviction_count"], tags=tags)
    statsd_client.gauge("slack.thread.hit_rate", metrics.get_hit_rate(), tags=tags)


def log_thread_metrics(
    channel: SlackChannel,
    user_id: str | None = None,
) -> None:
    """Log thread tracker metrics for debugging or simple monitoring.

    Args:
        channel: SlackChannel instance
        user_id: Optional user ID for SaaS scenarios

    Example:
        log_thread_metrics(slack_channel, user_id="user_123")
    """
    metrics = channel.thread_tracker_metrics

    logger.info(
        "Slack thread tracker metrics",
        extra={
            "user_id": user_id or "default",
            "hit_count": metrics.hit_count,
            "miss_count": metrics.miss_count,
            "hit_rate": f"{metrics.get_hit_rate():.2%}",
            "current_size": metrics.current_size,
            "lru_eviction_count": metrics.lru_eviction_count,
            "ttl_eviction_count": metrics.ttl_eviction_count,
        },
    )


def get_thread_metrics_summary(channel: SlackChannel) -> dict[str, object]:
    """Get a summary dict for API responses or dashboards.

    Args:
        channel: SlackChannel instance

    Returns:
        Dictionary with human-readable metrics

    Example:
        summary = get_thread_metrics_summary(slack_channel)
        return JSONResponse(summary)
    """
    metrics = channel.thread_tracker_metrics

    return {
        "hit_count": metrics.hit_count,
        "miss_count": metrics.miss_count,
        "hit_rate": f"{metrics.get_hit_rate():.2%}",
        "current_size": metrics.current_size,
        "lru_evictions": metrics.lru_eviction_count,
        "ttl_evictions": metrics.ttl_eviction_count,
        "total_requests": metrics.hit_count + metrics.miss_count,
    }
