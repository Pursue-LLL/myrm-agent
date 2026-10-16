"""Memory retrieval trace runs for the memory command center.

[INPUT]
app.schemas.memory.command_center::MemoryCommandTimelineEvent, MemoryCommandTraceRun, MemoryCommandTraceStep (POS: 记忆指挥中心 API Schema 层)
app.services.memory.command_center.command_center_projection_utils::optional_float, optional_str (POS: 指挥中心轻量数值解析)

[OUTPUT]
build_trace_runs: groups ledger retrieval-trace timeline events into the most recent trace runs.

[POS]
个人大脑指挥中心的检索追踪投影。把账本中带 trace_id 的检索步骤事件聚合为运行级 trace run，并推导每个 run 的状态、耗时与结果数。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.memory.command_center import (
    MemoryCommandTimelineEvent,
    MemoryCommandTraceRun,
    MemoryCommandTraceStep,
)
from app.services.memory.command_center.command_center_projection_utils import optional_float, optional_str

TraceStatus = Literal["success", "warning", "error", "skipped"]

TRACE_SOURCE = "memory_retrieval_trace"
TRACE_RUN_LIMIT = 6
TRACE_STEP_LIMIT = 16
_TRACE_STATUSES: tuple[TraceStatus, ...] = ("success", "warning", "error", "skipped")


def build_trace_runs(timeline: list[MemoryCommandTimelineEvent]) -> list[MemoryCommandTraceRun]:
    grouped: dict[str, list[MemoryCommandTimelineEvent]] = {}
    for event in timeline:
        if event.source != TRACE_SOURCE:
            continue
        trace_id = optional_str(event.metadata.get("trace_id")) or event.id
        grouped.setdefault(trace_id, []).append(event)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: max(event.occurred_at for event in item[1]),
        reverse=True,
    )
    return [_events_to_trace_run(trace_id, events) for trace_id, events in ordered_groups[:TRACE_RUN_LIMIT]]


def _events_to_trace_run(trace_id: str, events: list[MemoryCommandTimelineEvent]) -> MemoryCommandTraceRun:
    ordered_events = sorted(events, key=_step_sort_key)
    steps = [
        MemoryCommandTraceStep(
            id=event.id,
            phase=optional_str(event.metadata.get("step_phase")) or event.kind,
            status=_trace_status(event.status),
            title=optional_str(event.metadata.get("step_title")) or event.title,
            description=event.description,
            occurred_at=event.occurred_at,
            duration_ms=optional_float(event.metadata.get("duration_ms")),
            output_count=_metadata_int(event, "output_count") or 0,
            result_count=_metadata_int(event, "result_count") or 0,
            step_index=_metadata_int(event, "step_index") or index,
        )
        for index, event in enumerate(ordered_events[:TRACE_STEP_LIMIT])
    ]
    return MemoryCommandTraceRun(
        id=f"trace-run:{trace_id}",
        trace_id=trace_id,
        message_id=_first_metadata_str(ordered_events, "message_id"),
        chat_id=_first_metadata_str(ordered_events, "chat_id"),
        query_preview=_first_metadata_str(ordered_events, "query_preview") or "",
        status=_trace_run_status(ordered_events),
        occurred_at=max(event.occurred_at for event in ordered_events),
        duration_ms=_trace_run_duration_ms(ordered_events),
        result_count=max((_metadata_int(event, "result_count") or 0) for event in ordered_events),
        steps=steps,
    )


def _metadata_int(event: MemoryCommandTimelineEvent, key: str) -> int | None:
    value = event.metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _first_metadata_str(events: list[MemoryCommandTimelineEvent], key: str) -> str | None:
    for event in events:
        value = optional_str(event.metadata.get(key))
        if value:
            return value
    return None


def _step_sort_key(event: MemoryCommandTimelineEvent) -> tuple[int, datetime]:
    step_index = _metadata_int(event, "step_index")
    return (step_index if step_index is not None else TRACE_STEP_LIMIT, event.occurred_at)


def _trace_status(status: str) -> TraceStatus:
    for known in _TRACE_STATUSES:
        if status == known:
            return known
    return "warning"


def _trace_run_status(events: list[MemoryCommandTimelineEvent]) -> TraceStatus:
    statuses = {_trace_status(event.status) for event in events}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    if "success" in statuses:
        return "success"
    return "skipped"


def _trace_run_duration_ms(events: list[MemoryCommandTimelineEvent]) -> float | None:
    durations = [duration for event in events if (duration := optional_float(event.metadata.get("duration_ms"))) is not None]
    return max(durations) if durations else None
