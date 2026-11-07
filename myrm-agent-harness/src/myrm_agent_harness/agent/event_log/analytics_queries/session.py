"""[INPUT]
- .common::_collect_events / _durations / _failure_reasons (POS: 查询共用助手)
- .types (POS: 分析结果类型)
- event_log.protocols::EventLogBackend (POS: 事件日志后端协议)

[OUTPUT]
- get_session_summary / _extract_security_audit_summary

[POS]
`event_log/analytics_queries/` 的会话级聚合查询。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..types import (
    EventFilter,
    SessionAnalytics,
    SessionEvent,
    ToolBreakdown,
)
from .common import _collect_events

if TYPE_CHECKING:
    from ..protocols import EventLogBackend

async def get_session_summary(
    backend: EventLogBackend, session_id: str, *, events_limit: int = 150, timeline_limit: int = 100
) -> SessionAnalytics:
    """Aggregate session analytics with full tool/session_end coverage."""
    timeline_events = await _collect_events(backend.get_events(session_id, EventFilter(limit=events_limit)))
    tool_events = await _collect_events(
        backend.get_events(session_id, EventFilter(event_types=frozenset({"tool_start", "tool_end"})))
    )
    session_end_events = await _collect_events(
        backend.get_events(session_id, EventFilter(event_types=frozenset({"session_end"}), limit=1))
    )

    events_timeline = [
        SessionEvent(event_type=event.event_type, timestamp=event.timestamp, data=event.data)
        for event in timeline_events[:timeline_limit]
    ]

    duration_ms = 0.0
    task_metrics: dict[str, object] = {}
    token_economics: dict[str, object] | None = None
    if session_end_events:
        summary_data = session_end_events[0].data.get("summary", {})
        if isinstance(summary_data, dict):
            duration_ms = float(summary_data.get("duration_ms", 0))
            raw_task_metrics = summary_data.get("task_metrics")
            if isinstance(raw_task_metrics, dict):
                task_metrics = raw_task_metrics
            elif summary_data.get("compactions"):
                task_metrics = {"compression_count": int(summary_data.get("compactions", 0))}
            raw_token_economics = summary_data.get("token_economics")
            if isinstance(raw_token_economics, dict):
                token_economics = raw_token_economics

    tool_calls: dict[str, dict[str, Any]] = {}
    pending_starts: dict[str, int] = {}
    for event in tool_events:
        tool_name = event.data.get("tool_name")
        if not isinstance(tool_name, str):
            continue

        if event.event_type == "tool_start":
            bucket = tool_calls.setdefault(
                tool_name,
                {
                    "tool_name": tool_name,
                    "call_count": 0,
                    "total_duration_ms": 0.0,
                },
            )
            bucket["call_count"] = int(bucket["call_count"]) + 1
            pending_starts[tool_name] = pending_starts.get(tool_name, 0) + 1
        elif event.event_type == "tool_end" and tool_name in tool_calls:
            tool_calls[tool_name]["total_duration_ms"] = float(tool_calls[tool_name]["total_duration_ms"]) + float(
                event.data.get("duration_ms", 0)
            )
            if pending_starts.get(tool_name, 0) > 0:
                pending_starts[tool_name] -= 1

    tool_breakdown = [
        ToolBreakdown(
            tool_name=str(bucket["tool_name"]),
            call_count=int(bucket["call_count"]),
            total_duration_ms=float(bucket["total_duration_ms"]),
        )
        for bucket in tool_calls.values()
    ]
    security_audit = await _extract_security_audit_summary(backend, session_id)

    return SessionAnalytics(
        session_id=session_id,
        duration_ms=duration_ms,
        tool_breakdown=tool_breakdown,
        events_timeline=events_timeline,
        task_metrics=task_metrics,
        token_economics=token_economics,
        security_audit=security_audit,
    )

async def _extract_security_audit_summary(backend: EventLogBackend, session_id: str) -> dict[str, object] | None:
    """Extract security audit summary from persisted security_audit events."""
    audit_events = await _collect_events(
        backend.get_events(session_id, EventFilter(event_types=frozenset({"security_audit"}), limit=1))
    )
    if not audit_events:
        return None
    decisions = audit_events[0].data.get("decisions")
    if not isinstance(decisions, list):
        return None
    decision_counts: dict[str, int] = {}
    for d in decisions:
        if isinstance(d, dict):
            kind = d.get("decision", "UNKNOWN")
            decision_counts[kind] = decision_counts.get(kind, 0) + 1
    return {
        "total": len(decisions),
        "breakdown": decision_counts,
    }
