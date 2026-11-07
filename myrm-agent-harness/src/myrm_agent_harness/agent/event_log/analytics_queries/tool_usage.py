"""[INPUT]
- .common::_collect_events / _durations / _failure_reasons (POS: 查询共用助手)
- .types (POS: 分析结果类型)
- event_log.protocols::EventLogBackend (POS: 事件日志后端协议)

[OUTPUT]
- get_tool_usage_stats / get_global_tool_stability / get_agent_tool_health

[POS]
`event_log/analytics_queries/` 的工具使用与稳定性查询。
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from ..types import (
    EventFilter,
    ToolStabilityAnalytics,
    ToolStabilityDaily,
    ToolUsageStats,
)
from .common import _collect_events, _durations, _failure_reasons

if TYPE_CHECKING:
    from ..protocols import EventLogBackend

async def get_tool_usage_stats(
    backend: EventLogBackend, session_id: str, *, time_range_seconds: float | None = None
) -> list[ToolUsageStats]:
    """Query tool usage statistics for a single session."""
    start_time = time.time() - time_range_seconds if time_range_seconds is not None else None
    event_filter = EventFilter(
        event_types=frozenset(
            {
                "tool_start",
                "tool_end",
                "tool_failure",
                "tool_cancelled",
                "tool_timeout",
                "tool_retry",
                "tool_token_usage",
            }
        ),
        start_time=start_time,
    )

    tool_data: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "total": 0,
            "success": 0,
            "failure": 0,
            "timeout": 0,
            "retry": 0,
            "durations": [],
            "failure_reasons": Counter(),
            "tokens": 0,
        }
    )

    for event in await _collect_events(backend.get_events(session_id, event_filter)):
        tool_name = event.data.get("tool_name")
        if not isinstance(tool_name, str):
            continue

        data = tool_data[tool_name]
        if event.event_type == "tool_start":
            data["total"] = cast(int, data["total"]) + 1
        elif event.event_type == "tool_end":
            data["success"] = cast(int, data["success"]) + 1
            duration_ms = event.data.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                _durations(data).append(float(duration_ms))
        elif event.event_type == "tool_failure":
            data["failure"] = cast(int, data["failure"]) + 1
            duration_ms = event.data.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                _durations(data).append(float(duration_ms))
            reason = event.data.get("error_code") or event.data.get("error") or "<no_error_info>"
            _failure_reasons(data)[str(reason if isinstance(reason, str) else type(reason).__name__)] += 1
        elif event.event_type == "tool_cancelled":
            duration_ms = event.data.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                _durations(data).append(float(duration_ms))
        elif event.event_type == "tool_timeout":
            data["timeout"] = cast(int, data["timeout"]) + 1
        elif event.event_type == "tool_retry":
            data["retry"] = cast(int, data["retry"]) + 1
        elif event.event_type == "tool_token_usage":
            tokens = event.data.get("tokens")
            if isinstance(tokens, (int, float)):
                data["tokens"] = cast(int, data["tokens"]) + int(tokens)

    results: list[ToolUsageStats] = []
    for tool_name, data in tool_data.items():
        durations = _durations(data)
        total_calls = cast(int, data["total"])
        total_tokens = cast(int, data["tokens"])
        avg_duration_ms = sum(durations) / len(durations) if durations else 0.0
        avg_tokens = float(total_tokens) / float(total_calls) if total_calls > 0 else 0.0
        results.append(
            ToolUsageStats(
                tool_name=tool_name,
                total_calls=total_calls,
                success_count=cast(int, data["success"]),
                failure_count=cast(int, data["failure"]),
                timeout_count=cast(int, data["timeout"]),
                retry_count=cast(int, data["retry"]),
                avg_duration_ms=avg_duration_ms,
                failure_reasons=dict(_failure_reasons(data)),
                total_tokens=total_tokens,
                avg_tokens=avg_tokens,
            )
        )

    results.sort(key=lambda item: item.total_calls, reverse=True)
    return results

async def get_global_tool_stability(
    backend: EventLogBackend, session_ids: list[str], *, tool_name: str | None = None, start_time: float | None = None
) -> ToolStabilityAnalytics:
    """Calculate global tool stability metrics aggregated by day across multiple sessions.

    Args:
        backend: The EventLogBackend instance
        session_ids: List of session IDs to query
        tool_name: Optional tool name to filter by. If None, aggregates all tools.
        start_time: Optional start time filter (UTC timestamp)
    """
    import asyncio
    import math
    from datetime import UTC

    event_filter = EventFilter(
        event_types=frozenset({"tool_start", "tool_end", "tool_failure", "tool_timeout"}), start_time=start_time
    )

    # Dictionary to aggregate metrics by (date, tool_name).
    daily_data: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {
            "total": 0,
            "success": 0,
            "failure": 0,
            "timeout": 0,
            "durations": [],
            "reasons": Counter(),
        }
    )

    # Track overall busiest and most failed tool
    global_tool_totals: Counter[str] = Counter()
    global_tool_failures: Counter[str] = Counter()

    tasks = [backend.get_events(session_id, event_filter) for session_id in session_ids]
    all_session_events = await asyncio.gather(*tasks)

    for events in all_session_events:
        for event in await _collect_events(events):
            event_tool_name = event.data.get("tool_name")
            if not isinstance(event_tool_name, str):
                continue

            if tool_name and event_tool_name != tool_name:
                continue

            dt = datetime.fromtimestamp(event.timestamp, tz=UTC)
            date_str = dt.strftime("%Y-%m-%d")
            data = daily_data[(date_str, event_tool_name)]

            if event.event_type == "tool_start":
                data["total"] = cast(int, data["total"]) + 1
                global_tool_totals[event_tool_name] += 1
            elif event.event_type == "tool_end":
                data["success"] = cast(int, data["success"]) + 1
                duration_ms = event.data.get("duration_ms")
                if isinstance(duration_ms, (int, float)):
                    _durations(data).append(float(duration_ms))
            elif event.event_type == "tool_failure":
                data["failure"] = cast(int, data["failure"]) + 1
                global_tool_failures[event_tool_name] += 1
                duration_ms = event.data.get("duration_ms")
                if isinstance(duration_ms, (int, float)):
                    _durations(data).append(float(duration_ms))
                reason = event.data.get("error_code") or event.data.get("error") or "<unknown_failure>"
                _failure_reasons(data)[str(reason if isinstance(reason, str) else type(reason).__name__)] += 1
            elif event.event_type == "tool_timeout":
                data["timeout"] = cast(int, data["timeout"]) + 1
                global_tool_failures[event_tool_name] += 1
                _failure_reasons(data)["timeout"] += 1

    # Calculate global totals
    global_total_calls = sum(global_tool_totals.values())
    global_total_failures = sum(global_tool_failures.values())
    global_failure_rate = min(global_total_failures / global_total_calls, 1.0) if global_total_calls > 0 else 0.0

    busiest_tool = global_tool_totals.most_common(1)[0][0] if global_tool_totals else None
    most_failed_tool = global_tool_failures.most_common(1)[0][0] if global_tool_failures else None

    all_durations: list[float] = []

    # Build daily stability list (grouped by date + tool_name)
    daily_stability: list[ToolStabilityDaily] = []
    for date_str, entry_tool_name in sorted(daily_data.keys()):
        data = daily_data[(date_str, entry_tool_name)]

        total_calls = cast(int, data["total"])
        failure_count = cast(int, data["failure"])
        timeout_count = cast(int, data["timeout"])
        total_failures = failure_count + timeout_count

        durations = _durations(data)
        durations.sort()
        all_durations.extend(durations)

        avg_duration_ms = sum(durations) / len(durations) if durations else 0.0

        def get_percentile(arr: list[float], p: float) -> float:
            if not arr:
                return 0.0
            idx = math.ceil(p * len(arr)) - 1
            return arr[max(0, min(idx, len(arr) - 1))]

        p90_duration_ms = get_percentile(durations, 0.90)
        p99_duration_ms = get_percentile(durations, 0.99)
        failure_rate = min(total_failures / total_calls, 1.0) if total_calls > 0 else 0.0

        daily_stability.append(
            ToolStabilityDaily(
                date=date_str,
                tool_name=entry_tool_name,
                total_calls=total_calls,
                success_count=cast(int, data["success"]),
                failure_count=failure_count,
                timeout_count=timeout_count,
                avg_duration_ms=avg_duration_ms,
                p90_duration_ms=p90_duration_ms,
                p99_duration_ms=p99_duration_ms,
                failure_rate=failure_rate,
                failure_reasons=dict(_failure_reasons(data).most_common(10)),
            )
        )

    global_avg_duration_ms = sum(all_durations) / len(all_durations) if all_durations else 0.0

    return ToolStabilityAnalytics(
        daily_stability=daily_stability,
        global_total_calls=global_total_calls,
        global_failure_rate=global_failure_rate,
        global_avg_duration_ms=global_avg_duration_ms,
        busiest_tool=busiest_tool,
        most_failed_tool=most_failed_tool,
    )

async def get_agent_tool_health(backend: EventLogBackend, agent_id: str, *, days: int = 7) -> list[dict[str, Any]]:
    """Get aggregated tool health metrics for a specific agent.

    Args:
        backend: The EventLogBackend instance
        agent_id: The agent ID
        days: Lookback period in days

    Returns:
        List of dictionaries containing aggregated metrics per tool.
    """
    import asyncio
    import time

    start_time = time.time() - (days * 24 * 3600)
    event_filter = EventFilter(
        event_types=frozenset({"tool_start", "tool_end", "tool_failure", "tool_timeout"}), start_time=start_time
    )

    # Dictionary to aggregate metrics by tool_name.
    # tool_name -> {"total_calls": 0, "success_count": 0, "error_count": 0, "durations": []}
    tool_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_calls": 0, "success_count": 0, "error_count": 0, "durations": []}
    )

    session_ids = await backend.get_all_session_ids()
    tasks = [backend.get_events(session_id, event_filter) for session_id in session_ids]
    all_session_events = await asyncio.gather(*tasks)

    for events in all_session_events:
        for event in await _collect_events(events):
            if event.data.get("_agent_id") != agent_id:
                continue

            tool_name = event.data.get("tool_name")
            if not isinstance(tool_name, str):
                continue

            data = tool_data[tool_name]
            if event.event_type == "tool_start":
                data["total_calls"] = cast(int, data["total_calls"]) + 1
            elif event.event_type == "tool_end":
                data["success_count"] = cast(int, data["success_count"]) + 1
                duration_ms = event.data.get("duration_ms")
                if isinstance(duration_ms, (int, float)):
                    _durations(data).append(float(duration_ms))
            elif event.event_type in {"tool_failure", "tool_timeout"}:
                data["error_count"] = cast(int, data["error_count"]) + 1
                duration_ms = event.data.get("duration_ms")
                if isinstance(duration_ms, (int, float)):
                    _durations(data).append(float(duration_ms))

    results: list[dict[str, Any]] = []
    for tool_name, data in tool_data.items():
        durations = _durations(data)
        avg_duration = (sum(durations) / len(durations) / 1000.0) if durations else 0.0
        max_duration = (max(durations) / 1000.0) if durations else 0.0

        results.append(
            {
                "tool_name": tool_name,
                "total_calls": data["total_calls"],
                "success_count": data["success_count"],
                "error_count": data["error_count"],
                "avg_duration": avg_duration,
                "max_duration": max_duration,
            }
        )

    # Sort by total_calls descending
    results.sort(key=lambda item: item["total_calls"], reverse=True)
    return results
