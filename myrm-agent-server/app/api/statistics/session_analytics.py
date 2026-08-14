"""Session-level analytics and execution trace endpoints.

[INPUT]
- app.api.statistics.context_health (POS: 上下文健康指标构建)
- app.api.statistics.usage_aggregation (POS: 使用量聚合)
- myrm_agent_harness.agent.event_log (POS: 事件日志分析框架)
- app.core.utils.session_id::is_safe_session_id (POS: session_id/chat_id 文件路径插值白名单校验)

[OUTPUT]
- router: Session analytics APIRouter (get_session_analytics, get_session_execution_trace)

[POS]
会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.types import EventFilter
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.context_health import (
    build_chat_compaction_snapshot,
    build_context_health,
)
from app.api.statistics.usage_aggregation import aggregate_usage, normalize_usage_rows
from app.config.settings import settings
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.core.utils.session_id import is_safe_session_id
from app.database.connection import get_db
from app.database.models import Chat, Message
from app.services.memory.command_center.command_center_projection_utils import event_phase
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

router = APIRouter()
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
        "memory_events": memory_events,
        "total_events": 0,
        "total_tokens": 0,
    }


def _validate_session_id(session_id: str) -> None:
    """Reject IDs outside the safe charset as not-found (no existence oracle)."""
    if not is_safe_session_id(session_id):
        raise not_found_error(resource=f"Session {session_id}")


@router.get("/session/{session_id}")
async def get_session_analytics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get comprehensive analytics for a single session.

    Returns detailed breakdown of tokens, cost, tool usage, events timeline, and task metrics.
    Validates session ownership to prevent data leakage.
    """
    try:
        _validate_session_id(session_id)
        chat_stmt = select(Chat).where(and_(Chat.id == session_id))
        chat_result = await db.execute(chat_stmt)
        chat = chat_result.scalar_one_or_none()

        if not chat:
            raise not_found_error(resource=f"Session {session_id}")

        async def get_chat_metadata() -> dict[str, object]:
            return {
                "session_id": chat.id,
                "title": chat.title or "Untitled",
                "action_mode": chat.action_mode,
                "created_at": chat.created_at.isoformat() if chat.created_at else None,
            }

        async def get_message_stats() -> dict[str, object]:
            msg_stmt = select(
                func.count(Message.id).label("total_messages"),
                func.sum(case((Message.role == "user", 1), else_=0)).label(
                    "user_messages"
                ),
                func.sum(case((Message.role == "assistant", 1), else_=0)).label(
                    "assistant_messages"
                ),
            ).where(Message.chat_id == session_id)
            msg_result = await db.execute(msg_stmt)
            row = msg_result.one()

            usage_stmt = select(Message.extra_data).where(
                and_(
                    Message.chat_id == session_id,
                    Message.role == "assistant",
                    Message.extra_data.isnot(None),
                )
            )
            usage_result = await db.execute(usage_stmt)
            usage_rows = normalize_usage_rows(usage_result.all())
            stats = aggregate_usage(usage_rows)

            return {
                "message_count": row.total_messages or 0,
                "user_messages": row.user_messages or 0,
                "assistant_messages": row.assistant_messages or 0,
                **stats,
            }

        async def get_event_log_data() -> dict[str, object]:
            event_log_file = (
                Path(settings.database.event_log_dir) / f"{session_id}.jsonl"
            )
            if not event_log_file.exists():
                return {
                    "duration_ms": 0,
                    "tool_breakdown": [],
                    "events_timeline": [],
                    "task_metrics": {},
                }

            from myrm_agent_harness.agent.event_log import EventLogger

            backend = FileEventLogBackend(
                log_dir=Path(settings.database.event_log_dir), session_id=session_id
            )
            event_logger = EventLogger(backend=backend, session_id=session_id)
            summary = await event_logger.get_session_summary(
                events_limit=150, timeline_limit=100
            )

            tool_breakdown = [
                {
                    "tool_name": tb.tool_name,
                    "call_count": tb.call_count,
                    "total_duration_ms": tb.total_duration_ms,
                }
                for tb in summary.tool_breakdown
            ]

            events_timeline = [
                {
                    "type": se.event_type,
                    "timestamp": se.timestamp,
                    "data": se.data,
                }
                for se in summary.events_timeline
            ]

            result: dict[str, object] = {
                "duration_ms": summary.duration_ms,
                "tool_breakdown": tool_breakdown,
                "events_timeline": events_timeline,
                "task_metrics": summary.task_metrics,
                "token_economics": summary.token_economics,
            }
            if summary.security_audit:
                result["security_audit"] = summary.security_audit
            return result

        chat_meta, message_stats, event_log_data = await asyncio.gather(
            get_chat_metadata(),
            get_message_stats(),
            get_event_log_data(),
        )

        raw_task_metrics = event_log_data["task_metrics"]
        task_metrics_for_health: dict[str, object] = (
            {str(k): v for k, v in raw_task_metrics.items()}
            if isinstance(raw_task_metrics, dict)
            else {}
        )

        result = {
            **chat_meta,
            **message_stats,
            "duration_ms": event_log_data["duration_ms"],
            "tool_breakdown": event_log_data["tool_breakdown"],
            "events_timeline": event_log_data["events_timeline"],
            "task_metrics": event_log_data["task_metrics"],
            "token_economics": event_log_data.get("token_economics"),
            "context_health": build_context_health(
                message_stats=message_stats,
                task_metrics=task_metrics_for_health,
                chat_compaction=build_chat_compaction_snapshot(
                    compacted_at=chat.compacted_at,
                    compacted_tokens_saved=chat.compacted_tokens_saved,
                ),
                model_name=_dominant_model_name(message_stats),
            ).to_dict(),
        }

        return success_response(data=result)

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise internal_error(operation="Get session analytics", exception=e) from e


def _dominant_model_name(message_stats: dict[str, object]) -> str | None:
    model_breakdown = message_stats.get("modelBreakdown")
    if not isinstance(model_breakdown, dict):
        return None

    selected_model: str | None = None
    selected_calls = -1
    selected_tokens = -1
    for model_name, raw_bucket in model_breakdown.items():
        if not isinstance(model_name, str) or not isinstance(raw_bucket, dict):
            continue
        calls = _non_negative_int(raw_bucket.get("calls"))
        tokens = _non_negative_int(raw_bucket.get("inputTokens"))
        if calls > selected_calls or (
            calls == selected_calls and tokens > selected_tokens
        ):
            selected_model = model_name
            selected_calls = calls
            selected_tokens = tokens
    return selected_model


def _non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


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
        return

    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        call_id = tool_call.get("tool_call_id")
        if isinstance(call_id, str) and call_id in by_call_id:
            tool_call["security_labels"] = by_call_id[call_id]


@router.get("/session/{session_id}/trace")
async def get_session_execution_trace(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get structured execution trace for task-level replay.

    Returns the complete execution flow (input -> tool calls -> errors -> output)
    reconstructed from the event log, suitable for timeline visualization.
    """
    try:
        _validate_session_id(session_id)
        event_log_file = Path(settings.database.event_log_dir) / f"{session_id}.jsonl"
        chat_stmt = select(Chat.id).where(and_(Chat.id == session_id))
        chat_result = await db.execute(chat_stmt)
        has_chat = chat_result.scalar_one_or_none() is not None
        if not has_chat and not event_log_file.exists():
            raise not_found_error(resource=f"Session {session_id}")

        memory_events = await _build_session_memory_events(db, session_id)

        if not event_log_file.exists():
            return success_response(
                data=_empty_trace_payload(session_id, memory_events)
            )

        backend = FileEventLogBackend(
            log_dir=Path(settings.database.event_log_dir), session_id=session_id
        )
        trace = await build_trace(backend, session_id)
        trace_data = trace.to_dict()
        await _attach_security_labels(backend, session_id, trace_data)
        trace_data["memory_events"] = memory_events
        return success_response(data=trace_data)

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise internal_error(
            operation="Get session execution trace", exception=e
        ) from e
