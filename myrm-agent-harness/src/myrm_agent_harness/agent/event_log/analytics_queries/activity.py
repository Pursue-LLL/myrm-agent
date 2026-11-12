"""[INPUT]
- .common::_collect_events / _durations (POS: 查询共用助手)
- .types (POS: 分析结果类型)
- event_log.protocols::EventLogBackend (POS: 事件日志后端协议)

[OUTPUT]
- get_activity_patterns / get_bash_audit_logs / get_bash_execution_stats

[POS]
`event_log/analytics_queries/` 的活动模式与 bash 审计查询。
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, cast

from ..types import (
    ActivityPatterns,
    BashExecutionStats,
    EventFilter,
    HourlyToolUsage,
    StructuredEvent,
)
from .common import _collect_events, _durations

if TYPE_CHECKING:
    from ..protocols import EventLogBackend

async def get_activity_patterns(
    backend: EventLogBackend, session_id: str, *, time_range_seconds: float | None = None
) -> ActivityPatterns:
    """Query per-hour activity patterns for a single session."""
    start_time = time.time() - time_range_seconds if time_range_seconds is not None else None
    event_filter = EventFilter(
        event_types=frozenset({"tool_start", "tool_end", "tool_failure", "tool_cancelled"}), start_time=start_time
    )

    hourly_data: dict[tuple[int, str], dict[str, object]] = defaultdict(lambda: {"count": 0, "durations": []})
    for event in await _collect_events(backend.get_events(session_id, event_filter)):
        tool_name = event.data.get("tool_name")
        if not isinstance(tool_name, str):
            continue

        hour = datetime.fromtimestamp(event.timestamp).hour
        data = hourly_data[(hour, tool_name)]
        if event.event_type == "tool_start":
            data["count"] = cast(int, data["count"]) + 1

        if event.event_type in {"tool_end", "tool_failure", "tool_cancelled"}:
            duration_ms = event.data.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                _durations(data).append(float(duration_ms))

    hourly_breakdown: list[HourlyToolUsage] = []
    hour_totals: dict[int, int] = defaultdict(int)
    tool_totals: dict[str, int] = defaultdict(int)

    for (hour, tool_name), data in hourly_data.items():
        call_count = cast(int, data["count"])
        durations = _durations(data)
        avg_duration_ms = sum(durations) / len(durations) if durations else 0.0
        hourly_breakdown.append(
            HourlyToolUsage(hour=hour, tool_name=tool_name, call_count=call_count, avg_duration_ms=avg_duration_ms)
        )
        hour_totals[hour] += call_count
        tool_totals[tool_name] += call_count

    peak_hour = max(hour_totals, key=lambda k: hour_totals[k]) if hour_totals else 0
    peak_tool = max(tool_totals, key=lambda k: tool_totals[k]) if tool_totals else ""
    return ActivityPatterns(hourly_breakdown=hourly_breakdown, peak_hour=peak_hour, peak_tool=peak_tool)

async def get_bash_audit_logs(
    backend: EventLogBackend,
    session_id: str,
    *,
    start_time: float | None = None,
    end_time: float | None = None,
    command_type: str | None = None,
    risk_level: str | None = None,
    limit: int = 100,
) -> list[StructuredEvent]:
    """Query bash command audit logs for a single session."""
    event_filter = EventFilter(
        event_types=frozenset({"bash_command_executed"}), start_time=start_time, end_time=end_time, limit=limit
    )

    results: list[StructuredEvent] = []
    for event in await _collect_events(backend.get_events(session_id, event_filter)):
        if command_type and event.data.get("command_type") != command_type:
            continue
        if risk_level and event.data.get("risk_level") != risk_level:
            continue
        results.append(event)

    results.sort(key=lambda item: item.timestamp, reverse=True)
    return results[:limit]

async def get_bash_execution_stats(backend: EventLogBackend, session_id: str) -> BashExecutionStats:
    """Aggregate bash command execution statistics for a single session."""
    event_filter = EventFilter(event_types=frozenset({"bash_command_executed"}))

    total = 0
    success_count = 0
    durations: list[float] = []
    error_counter: Counter[str] = Counter()
    command_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    hour_counter: Counter[int] = Counter()

    for event in await _collect_events(backend.get_events(session_id, event_filter)):
        total += 1
        success = bool(event.data.get("success"))
        if success:
            success_count += 1

        duration_ms = event.data.get("duration_ms")
        if isinstance(duration_ms, (int, float)):
            durations.append(float(duration_ms))

        if not success:
            error_msg = event.data.get("error_message", "<unknown>")
            if isinstance(error_msg, str):
                error_counter[error_msg[:100]] += 1

        command = event.data.get("command")
        if isinstance(command, str):
            command_counter[command[:50]] += 1

        command_type = event.data.get("command_type")
        if isinstance(command_type, str):
            type_counter[command_type] += 1

        hour_counter[datetime.fromtimestamp(event.timestamp).hour] += 1

    success_rate = (success_count / total) if total > 0 else 0.0
    avg_duration_ms = (sum(durations) / len(durations)) if durations else 0.0
    return BashExecutionStats(
        total_commands=total,
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
        error_top10=error_counter.most_common(10),
        command_hotmap=command_counter.most_common(10),
        type_distribution=dict(type_counter),
        hourly_breakdown=sorted(hour_counter.items()),
    )
