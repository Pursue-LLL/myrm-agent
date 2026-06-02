from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.agent.event_log.analytics_queries import get_global_tool_stability
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import ToolStabilityAnalytics

from app.config.settings import settings

logger = logging.getLogger(__name__)


async def analyze_provider_health(
    provider_name: str,
    time_window_minutes: int = 5,
) -> dict[str, object]:
    """
    Analyze the health of a specific provider or tool based on recent event logs.
    Returns recommendations for routing degradation if health is poor.
    """
    try:
        if not Path(settings.database.event_log_dir).exists():
            return {"healthy": True, "reason": "No event logs available"}

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        session_ids = await backend.get_all_session_ids()

        import time

        start_time = time.time() - (time_window_minutes * 60)

        # We reuse the tool stability query, but we can filter by provider if tools are named accordingly
        # For this prototype, we'll just check the specific tool/provider name
        stability_data: ToolStabilityAnalytics = await get_global_tool_stability(
            backend, session_ids, tool_name=provider_name, start_time=start_time
        )

        if stability_data.global_total_calls < 5:
            # Not enough data to make a statistical decision
            return {"healthy": True, "reason": "Insufficient data"}

        if stability_data.global_failure_rate > 0.2:
            return {
                "healthy": False,
                "recommend_fallback": True,
                "reason": f"High failure rate ({stability_data.global_failure_rate * 100:.1f}%) in last {time_window_minutes} minutes",
                "metrics": {
                    "failure_rate": stability_data.global_failure_rate,
                    "avg_duration_ms": stability_data.global_avg_duration_ms,
                },
            }

        # Check P90 latency degradation (e.g., > 10s is bad)
        recent_p90 = 0.0
        if stability_data.daily_stability:
            recent_p90 = stability_data.daily_stability[-1].p90_duration_ms

        if recent_p90 > 10000:  # 10 seconds
            return {
                "healthy": False,
                "recommend_fallback": True,
                "reason": f"High P90 latency ({recent_p90}ms) indicating severe degradation",
                "metrics": {"failure_rate": stability_data.global_failure_rate, "p90_duration_ms": recent_p90},
            }

        return {"healthy": True, "reason": "Metrics within acceptable bounds"}

    except Exception as e:
        logger.warning(f"Failed to analyze provider health for {provider_name}: {e}")
        return {"healthy": True, "reason": "Analysis failed, assuming healthy"}
