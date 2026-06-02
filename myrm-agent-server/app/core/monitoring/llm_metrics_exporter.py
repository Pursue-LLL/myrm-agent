"""LLM Retry Metrics Prometheus Exporter.

业务层示例：展示如何将框架层的 EmptyRetryMetrics 导出到 Prometheus。

支持两种场景：
1. 独立部署：用户看自己的 metrics
2. SaaS 平台：平台看所有用户的 metrics（通过 user_id label 区分）
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms import ChatLiteLLM


def export_llm_retry_metrics_to_dict(llm: "ChatLiteLLM", user_id: str | None = None) -> dict[str, object]:
    """Export LLM retry metrics to dict (ready for Prometheus).

    Args:
        llm: ChatLiteLLM instance
        user_id: Optional user ID for SaaS multi-tenant scenario

    Returns:
        Dict with metrics (can be converted to Prometheus format)

    Example (Scenario 1: Single deployment):
        >>> from myrm_agent_harness.toolkits.llms import ChatLiteLLM
        >>> llm = ChatLiteLLM(model="gpt-4o-mini")
        >>> # ... make LLM calls ...
        >>> metrics = export_llm_retry_metrics_to_dict(llm)
        >>> # Export to Prometheus/DataDog/Logs

    Example (Scenario 2: SaaS platform):
        >>> metrics = export_llm_retry_metrics_to_dict(llm, user_id="user_123")
        >>> # Metrics will include user_id label
    """
    raw = llm.retry_metrics.to_dict()
    metrics: dict[str, object] = {}
    for key, val in raw.items():
        k = str(key)
        if isinstance(val, (int, float)):
            metrics[k] = float(val)
        elif isinstance(val, str):
            metrics[k] = val
        else:
            metrics[k] = val

    if user_id:
        metrics["user_id"] = user_id

    return metrics


def get_llm_retry_success_rate(llm: "ChatLiteLLM") -> float:
    """Get retry success rate (0.0-1.0).

    Useful for alerting: if success_rate < 0.5, trigger alert.

    Example:
        >>> success_rate = get_llm_retry_success_rate(llm)
        >>> if success_rate < 0.5 and llm.retry_metrics.get_total_retries() > 10:
        >>>     send_alert("High retry failure rate!")
    """
    return float(llm.retry_metrics.get_success_rate())


def get_llm_retry_stats_summary(llm: "ChatLiteLLM") -> dict[str, float]:
    """Get retry stats summary for dashboard.

    Returns:
        Dict with key metrics:
        - total_retries: Total retry attempts
        - total_successes: Successful retries
        - success_rate: Success rate (0.0-1.0)
        - avg_delay_ms: Average retry delay in ms

    Example:
        >>> stats = get_llm_retry_stats_summary(llm)
        >>> print(f"Total retries: {stats['total_retries']}")
        >>> print(f"Success rate: {stats['success_rate']:.2%}")
    """
    metrics = llm.retry_metrics
    return {
        "total_retries": float(metrics.get_total_retries()),
        "total_successes": float(metrics.get_total_successes()),
        "success_rate": float(metrics.get_success_rate()),
        "avg_delay_ms": float(metrics.get_avg_retry_delay_ms()),
    }
