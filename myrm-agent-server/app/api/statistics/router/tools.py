"""[INPUT]
- .common (POS: shared router)

[OUTPUT]
- get_tool_stability, get_agent_tool_health

[POS]
Statistics endpoints: tools.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventLogAnalytics
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend

from app.config.settings import settings
from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response

from .common import router


@router.get("/tool-stability")
async def get_tool_stability(
    tool_name: str | None = Query(
        None,
        description="Optional tool name to filter by. If omitted, aggregates all tools.",
    ),
    time_range_days: int | None = Query(30, ge=1, le=365, description="Time range in days (optional, defaults to 30)"),
) -> JSONResponse:
    """Get global tool stability and performance metrics.

    Returns daily aggregated tool stability statistics, including success/failure counts,
    timeouts, failure rates, P90/P99 latency, and top failure reasons.
    """
    try:
        if not Path(settings.database.event_log_dir).exists():
            return success_response(
                data={
                    "daily_stability": [],
                    "global_total_calls": 0,
                    "global_failure_rate": 0.0,
                    "global_avg_duration_ms": 0.0,
                    "busiest_tool": "unknown",
                    "most_failed_tool": "unknown",
                }
            )

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)

        stability_data = await analytics.get_tool_stability(
            tool_name=tool_name,
            time_range_days=time_range_days,
        )

        return success_response(
            data={
                "daily_stability": [
                    {
                        "date": ds.date,
                        "tool_name": ds.tool_name,
                        "total_calls": ds.total_calls,
                        "success_count": ds.success_count,
                        "failure_count": ds.failure_count,
                        "timeout_count": ds.timeout_count,
                        "avg_duration_ms": ds.avg_duration_ms,
                        "p90_duration_ms": ds.p90_duration_ms,
                        "p99_duration_ms": ds.p99_duration_ms,
                        "failure_rate": ds.failure_rate,
                        "failure_reasons": ds.failure_reasons,
                    }
                    for ds in stability_data.daily_stability
                ],
                "global_total_calls": stability_data.global_total_calls,
                "global_failure_rate": stability_data.global_failure_rate,
                "global_avg_duration_ms": stability_data.global_avg_duration_ms,
                "busiest_tool": stability_data.busiest_tool,
                "most_failed_tool": stability_data.most_failed_tool,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get tool stability patterns", exception=e) from e


@router.get("/agent/{agent_id}/tool_health")
async def get_agent_tool_health(
    agent_id: str,
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
) -> JSONResponse:
    """Get aggregated tool health metrics for a specific agent.

    Queries the EventLog backend to return aggregated success rates,
    error counts, and durations per tool for the specified agent.
    """
    try:
        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id="default")
        analytics = EventLogAnalytics(backend)
        health_data = await analytics.get_agent_tool_health(agent_id=agent_id, days=days)
        return success_response(data=health_data)
    except Exception as e:
        raise internal_error(operation="Get agent tool health", exception=e) from e
