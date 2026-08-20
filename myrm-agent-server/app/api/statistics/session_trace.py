"""Session execution trace endpoint.

[INPUT]
- myrm_agent_harness.agent.event_log.trace_builder (POS: 执行轨迹重建)
- myrm_agent_harness.agent.event_log.backends.file_backend (POS: 事件日志文件后端)
- app.services.memory.ledger.operation_ledger (POS: 记忆操作账本)
- app.services.memory.command_center.command_center_projection_utils::event_phase (POS: 事件阶段投影)

[OUTPUT]
- router: Session execution trace APIRouter (get_session_execution_trace)

[POS]
会话执行轨迹 API。从事件日志重建任务级执行流（输入 -> 工具调用 -> 错误 -> 输出），
并叠加记忆账本事件与步骤级安全决策标签，用于时间线回放。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.types import EventFilter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.session_analytics import _validate_session_id
from app.config.settings import settings
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat
from app.services.memory.command_center.command_center_projection_utils import (
    event_phase,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

router = APIRouter()
logger = logging.getLogger(__name__)


async def _build_session_memory_events(db: AsyncSession, session_id: str) -> list[dict[str, object]]:
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


async def _attach_security_labels(backend: FileEventLogBackend, session_id: str, trace_data: dict[str, object]) -> None:
    """Attach step-level security decisions to matching tool calls.

    Reads the session's ``security_audit`` event (batch-persisted at session end)
    and groups decisions by ``tool_call_id`` so each tool call in the trace
    carries the security labels that fired on it (deny / taint / injection / PII…).
    In-place mutation of ``trace_data["tool_calls"]``; no-op when no audit exists.
    """
    try:
        events = await backend.get_events(session_id, EventFilter(event_types=frozenset({"security_audit"})))
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
            return success_response(data=_empty_trace_payload(session_id, memory_events))

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id=session_id)
        trace = await build_trace(backend, session_id)
        trace_data = trace.to_dict()
        await _attach_security_labels(backend, session_id, trace_data)
        trace_data["memory_events"] = memory_events
        return success_response(data=trace_data)

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise internal_error(operation="Get session execution trace", exception=e) from e
