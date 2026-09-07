"""Session execution trace enrichment helpers.

[INPUT]
- myrm_agent_harness.agent.event_log.backends.file_backend (POS: 事件日志文件后端)
- myrm_agent_harness.agent.event_log.types::EventFilter (POS: 事件过滤)
- app.services.memory.ledger.operation_ledger (POS: 记忆操作账本)
- app.services.memory.command_center.command_center_projection_utils::event_phase (POS: 事件阶段投影)

[OUTPUT]
- _build_session_memory_events, _empty_trace_payload, _enrich_performance_and_gantt, _attach_security_labels

[POS]
提供执行轨迹与甘特图指标丰富、性能统计、安全标签关联以及记忆事件投影辅助。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory.command_center.command_center_projection_utils import (
    event_phase,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

logger = logging.getLogger(__name__)


async def _build_session_memory_events(
    db: AsyncSession, session_id: str
) -> list[dict[str, object]]:
    """Load session-scoped memory ledger events for replay overlay."""
    ledger = MemoryOperationLedgerService(db)
    rows = await ledger.list_events_for_session(session_id, limit=48)
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "phase": event_phase(row.kind),
            "status": row.status,
            "timestamp": row.occurred_at.timestamp(),
            "title": row.memory_type or row.kind,
            "summary": row.summary,
            "target_kind": row.target_kind,
            "target_id": row.target_id,
            "influence_count": len(row.influence_refs_json or []),
            "metadata": row.metadata_json or {},
        }
        for row in rows
    ]


def _empty_trace_payload(
    session_id: str, memory_events: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "metadata": {
            "user_id": None,
            "agent_id": None,
            "task_type": None,
            "trace_id": None,
        },
        "outcome": "unknown",
        "start_time": 0,
        "end_time": 0,
        "duration_ms": 0,
        "task_input": "",
        "output": "",
        "tool_calls": [],
        "llm_calls": [],
        "errors": [],
        "human_feedback": [],
        "anomalies": [],
        "memory_events": memory_events,
        "total_events": 0,
        "total_tokens": 0,
        "performance_summary": {
            "llm_duration_ms": 0.0,
            "tool_duration_ms": 0.0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cache_read_tokens": 0,
            "prompt_cache_hit_ratio": 0.0,
            "gantt_spans": [],
        },
    }


def _enrich_performance_and_gantt(trace_data: dict[str, object]) -> None:
    """Enrich trace with LLM vs Tool timing, Prompt Cache hit ratio, and Gantt spans."""
    llm_calls = trace_data.get("llm_calls") or []
    tool_calls = trace_data.get("tool_calls") or []

    total_llm_ms = 0.0
    total_prompt_tokens = 0
    total_cache_read_tokens = 0
    total_completion_tokens = 0

    gantt_spans: list[dict[str, object]] = []

    if isinstance(llm_calls, list):
        for lc in llm_calls:
            if not isinstance(lc, dict):
                continue
            dur = float(lc.get("duration_ms") or 0.0)
            total_llm_ms += dur
            prompt_t = int(lc.get("prompt_tokens") or 0)
            comp_t = int(lc.get("completion_tokens") or 0)
            cache_t = int(lc.get("cache_read_tokens") or 0)
            total_prompt_tokens += prompt_t
            total_completion_tokens += comp_t
            total_cache_read_tokens += cache_t

            start_t = float(lc.get("start_time") or 0.0)
            end_t = float(lc.get("end_time") or (start_t + dur / 1000.0))
            attempt_val = int(lc.get("attempt") or 1)
            retry_count_val = int(lc.get("retry_count") or 0)
            gantt_spans.append(
                {
                    "type": "llm",
                    "label": lc.get("model_name") or "LLM Inference",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_ms": dur,
                    "ttft_ms": lc.get("ttft_ms"),
                    "cache_read_tokens": cache_t,
                    "status": "success",
                    "attempt": attempt_val,
                    "retry_count": retry_count_val,
                }
            )

    total_tool_ms = 0.0
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            dur = float(tc.get("duration_ms") or 0.0)
            total_tool_ms += dur
            start_t = float(tc.get("start_time") or 0.0)
            end_t = float(tc.get("end_time") or (start_t + dur / 1000.0))
            gantt_spans.append(
                {
                    "type": "tool",
                    "label": tc.get("tool_name") or "Tool Call",
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration_ms": dur,
                    "status": "success" if tc.get("success", True) else "error",
                    "error": tc.get("error"),
                }
            )

    gantt_spans.sort(key=lambda x: float(x.get("start_time") or 0.0))

    hit_ratio = (
        round(total_cache_read_tokens / total_prompt_tokens, 4)
        if total_prompt_tokens > 0
        else 0.0
    )

    trace_data["performance_summary"] = {
        "llm_duration_ms": round(total_llm_ms, 2),
        "tool_duration_ms": round(total_tool_ms, 2),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_cache_read_tokens": total_cache_read_tokens,
        "prompt_cache_hit_ratio": hit_ratio,
        "gantt_spans": gantt_spans,
    }


async def _attach_security_labels(
    backend: FileEventLogBackend, session_id: str, trace_data: dict[str, object]
) -> None:
    """Attach step-level security decisions to matching tool calls.

    Reads the session's ``security_audit`` event (batch-persisted at session end)
    and groups decisions by ``tool_call_id`` so each tool call in the trace
    carries the security labels that fired on it (deny / taint / injection / PII…).
    In-place mutation of ``trace_data["tool_calls"]``; no-op when no audit exists.
    """
    try:
        events = await backend.get_events(
            session_id, EventFilter(event_types=frozenset({"security_audit"}))
        )
    except Exception:
        logger.debug("Failed to read security_audit events for lineage", exc_info=True)
        return

    tool_calls = trace_data.get("tool_calls")
    if not isinstance(tool_calls, list) or not events:
        return

    by_call_id: dict[str, list[dict[str, object]]] = {}
    for event in events:
        decisions = event.data.get("decisions")
        if not isinstance(decisions, list):
            continue
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            call_id = decision.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id:
                continue
            by_call_id.setdefault(call_id, []).append(
                {
                    "decision": decision.get("decision"),
                    "reason": decision.get("reason"),
                    "tainted": bool(decision.get("tainted")),
                    "ts": decision.get("ts"),
                }
            )

    if not by_call_id:
        logger.debug(
            "security_audit decisions for session %s carry no tool_call_id; cannot attach decisions to trace tool calls",
            session_id,
        )
        return

    matched_call_ids: set[str] = set()
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        call_id = tool_call.get("tool_call_id")
        if isinstance(call_id, str) and call_id in by_call_id:
            tool_call["security_labels"] = by_call_id[call_id]
            matched_call_ids.add(call_id)

    unmatched = sorted(set(by_call_id) - matched_call_ids)
    if unmatched:
        logger.debug(
            "security_audit tool_call_id(s) %s for session %s have no matching trace tool call; "
            "their decisions were not attached",
            unmatched,
            session_id,
        )
