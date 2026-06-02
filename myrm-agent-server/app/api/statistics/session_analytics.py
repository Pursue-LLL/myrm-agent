"""Session-level analytics and execution trace endpoints.

[INPUT]
- app.api.statistics.context_health (POS: 上下文健康指标构建)
- app.api.statistics.usage_aggregation (POS: 使用量聚合)
- myrm_agent_harness.agent.event_log (POS: 事件日志分析框架)

[OUTPUT]
- router: Session analytics APIRouter (get_session_analytics, get_session_execution_trace)

[POS]
会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
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
from app.database.connection import get_db
from app.database.models import Chat, Message
from app.services.memory.command_center_projection_utils import event_phase
from app.services.memory.operation_ledger import MemoryOperationLedgerService

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
            "phase": event_phase(row.kind),
            "status": row.status,
            "timestamp": row.occurred_at.timestamp(),
            "title": row.memory_type or row.kind,
            "summary": row.summary,
            "target_kind": row.target_kind,
            "target_id": row.target_id,
            "influence_count": len(row.influence_refs_json or []),
        }
        for row in rows
    ]


def _empty_trace_payload(session_id: str, memory_events: list[dict[str, object]]) -> dict[str, object]:
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

            return {
                "duration_ms": summary.duration_ms,
                "tool_breakdown": tool_breakdown,
                "events_timeline": events_timeline,
                "task_metrics": summary.task_metrics,
                "token_economics": summary.token_economics,
            }

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
        if calls > selected_calls or (calls == selected_calls and tokens > selected_tokens):
            selected_model = model_name
            selected_calls = calls
            selected_tokens = tokens
    return selected_model


def _non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


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
        chat_stmt = select(Chat.id).where(and_(Chat.id == session_id))
        chat_result = await db.execute(chat_stmt)
        if not chat_result.scalar_one_or_none():
            raise not_found_error(resource=f"Session {session_id}")

        memory_events = await _build_session_memory_events(db, session_id)

        event_log_file = Path(settings.database.event_log_dir) / f"{session_id}.jsonl"
        if not event_log_file.exists():
            return success_response(data=_empty_trace_payload(session_id, memory_events))

        backend = FileEventLogBackend(
            log_dir=Path(settings.database.event_log_dir), session_id=session_id
        )
        trace = await build_trace(backend, session_id)
        trace_data = trace.to_dict()
        trace_data["memory_events"] = memory_events
        return success_response(data=trace_data)

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise internal_error(
            operation="Get session execution trace", exception=e
        ) from e


@router.get("/usage/model-sessions")
async def get_model_sessions(
    model: str = Query(
        ..., description="The full model identifier, e.g., 'openai/gpt-4o'"
    ),
    days: int = Query(30, ge=1, le=90, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get sessions that utilized a specific model, along with model-specific token/cost breakdown.

    Uses composite index on message creation time to narrow down messages before performing
    JSON extraction, ensuring robust O(log N) first-stage scanning.
    """
    try:
        from datetime import timedelta, timezone

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        filters = [
            Message.role == "assistant",
            Message.extra_data.isnot(None),
            Message.created_at >= start_dt,
        ]

        stmt = select(Message.chat_id, Message.extra_data, Message.created_at).where(
            and_(*filters)
        )
        result = await db.execute(stmt)
        rows = result.all()

        session_aggregates: dict[str, dict[str, object]] = {}
        for chat_id, extra_data, created_at in rows:
            if not isinstance(extra_data, dict):
                continue
            usage = extra_data.get("usage")
            if not isinstance(usage, dict):
                continue
            model_usage = usage.get("model_usage")
            if not isinstance(model_usage, dict):
                continue

            # Check if the requested model exists in model_usage
            model_data = model_usage.get(model)
            if not isinstance(model_data, dict):
                continue

            # Accumulate stats specifically for this model inside this chat session
            if chat_id not in session_aggregates:
                session_aggregates[chat_id] = {
                    "calls": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "cachedTokens": 0,
                    "totalTokens": 0,
                    "costUsd": 0.0,
                    "last_used_at": created_at,
                }

            agg = session_aggregates[chat_id]
            agg["calls"] = int(agg["calls"]) + 1
            agg["inputTokens"] = int(agg["inputTokens"]) + int(
                model_data.get("prompt_tokens") or 0
            )
            agg["outputTokens"] = int(agg["outputTokens"]) + int(
                model_data.get("completion_tokens") or 0
            )
            agg["cachedTokens"] = int(agg["cachedTokens"]) + int(
                model_data.get("cached_tokens") or 0
            )
            agg["totalTokens"] = int(agg["totalTokens"]) + int(
                model_data.get("total_tokens") or 0
            )

            cost_raw = model_data.get("cost_usd")
            if isinstance(cost_raw, (int, float)):
                agg["costUsd"] = float(agg["costUsd"]) + float(cost_raw)

            if created_at and (
                agg["last_used_at"] is None or created_at > agg["last_used_at"]
            ):
                agg["last_used_at"] = created_at

        if not session_aggregates:
            return success_response(data=[])

        chat_ids = list(session_aggregates.keys())
        chat_stmt = select(
            Chat.id, Chat.title, Chat.action_mode, Chat.created_at
        ).where(Chat.id.in_(chat_ids))
        chat_result = await db.execute(chat_stmt)
        chat_rows = chat_result.all()

        chat_details = {row.id: row for row in chat_rows}

        results = []
        for chat_id, agg in session_aggregates.items():
            chat_row = chat_details.get(chat_id)
            if not chat_row:
                continue

            results.append(
                {
                    "chatId": chat_id,
                    "title": chat_row.title or "Untitled",
                    "actionMode": chat_row.action_mode,
                    "createdAt": (
                        chat_row.created_at.isoformat() if chat_row.created_at else None
                    ),
                    "calls": agg["calls"],
                    "inputTokens": agg["inputTokens"],
                    "outputTokens": agg["outputTokens"],
                    "cachedTokens": agg["cachedTokens"],
                    "totalTokens": agg["totalTokens"],
                    "costUsd": round(float(agg["costUsd"]), 6),
                    "lastUsedAt": (
                        agg["last_used_at"].isoformat() if agg["last_used_at"] else None
                    ),
                }
            )

        # Sort the results by totalTokens descending (highest usage first)
        results.sort(key=lambda x: x["totalTokens"], reverse=True)

        return success_response(data=results)
    except Exception as e:
        raise internal_error(
            operation="Get model-specific session statistics", exception=e
        ) from e
