"""Session execution trace endpoint.

[INPUT]
- myrm_agent_harness.agent.event_log.trace_builder (POS: 执行轨迹重建)
- myrm_agent_harness.agent.event_log.backends.file_backend (POS: 事件日志文件后端)
- app.api.statistics.session_trace_enrichment (POS: 轨迹丰富与性能甘特图辅助)

[OUTPUT]
- router: Session execution trace APIRouter (get_session_execution_trace, search_session_traces)

[POS]
会话执行轨迹 API。从事件日志重建任务级执行流（输入 -> 工具调用 -> 错误 -> 输出），
并叠加记忆账本事件与步骤级安全决策标签，用于时间线回放。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.infra.tracing import sanitize_trace_payload
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.session_analytics import _validate_session_id
from app.api.statistics.session_trace_enrichment import (
    _attach_security_labels,
    _build_session_memory_events,
    _empty_trace_payload,
    _enrich_performance_and_gantt,
)
from app.config.settings import settings
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat

router = APIRouter()
logger = logging.getLogger(__name__)


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
            return success_response(data=sanitize_trace_payload(_empty_trace_payload(session_id, memory_events)))

        backend = FileEventLogBackend(log_dir=Path(settings.database.event_log_dir), session_id=session_id)
        trace = await build_trace(backend, session_id)
        trace_data = trace.to_dict()
        await _attach_security_labels(backend, session_id, trace_data)
        _enrich_performance_and_gantt(trace_data)
        trace_data["memory_events"] = memory_events
        return success_response(data=sanitize_trace_payload(trace_data))

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise internal_error(operation="Get session execution trace", exception=e) from e


def _search_traces_sync(
    chats_meta: list[dict[str, object]],
    log_dir_str: str,
    query_lower: str,
    limit: int,
) -> list[dict[str, object]]:
    """Synchronous file scanner for trace search executed in worker thread to prevent event loop blocking."""
    log_dir = Path(log_dir_str)
    matched: list[dict[str, object]] = []

    for item in chats_meta:
        chat_id = str(item["id"])
        title = str(item.get("title") or "")
        created_at_iso = item.get("created_at")
        updated_at_iso = item.get("updated_at")

        log_file = log_dir / f"{chat_id}.jsonl"
        task_input = ""
        total_tokens = 0
        cache_read_tokens = 0
        prompt_tokens = 0

        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ev_type = ev.get("type") or ev.get("event_type")
                        data = ev.get("data") or {}
                        if not task_input and ev_type == "task_start":
                            task_input = str(data.get("input") or "")
                        elif ev_type in ("token_usage", "llm_end"):
                            u = data.get("usage") or data
                            if isinstance(u, dict):
                                p = int(u.get("prompt_tokens") or 0)
                                c = int(u.get("completion_tokens") or 0)
                                total_tokens += p + c
                                prompt_tokens += p
                                cd = 0
                                if det := u.get("prompt_tokens_details"):
                                    if isinstance(det, dict):
                                        cd = int(det.get("cached_tokens") or 0)
                                elif "cache_read_input_tokens" in u:
                                    cd = int(u.get("cache_read_input_tokens") or 0)
                                cache_read_tokens += cd
            except Exception:
                pass

        if query_lower:
            if query_lower not in title.lower() and query_lower not in task_input.lower():
                continue

        hit_ratio = round(cache_read_tokens / prompt_tokens, 4) if prompt_tokens > 0 else 0.0

        matched.append(
            {
                "session_id": chat_id,
                "title": title,
                "task_input": task_input[:200],
                "total_tokens": total_tokens,
                "cache_hit_ratio": hit_ratio,
                "created_at": created_at_iso,
                "updated_at": updated_at_iso,
            }
        )
        if len(matched) >= limit:
            break

    return matched


@router.get("/traces/search")
async def search_session_traces(
    query: str = "",
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Search traces by user task prompt or session title."""
    try:
        query_lower = query.strip().lower()
        if not query_lower:
            return success_response(data=[])

        stmt = select(Chat).order_by(Chat.updated_at.desc()).limit(limit * 2)
        result = await db.execute(stmt)
        chats = result.scalars().all()
        chats_meta = [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in chats
        ]

        matched = await asyncio.to_thread(
            _search_traces_sync,
            chats_meta,
            settings.database.event_log_dir,
            query_lower,
            limit,
        )

        return success_response(data=[sanitize_trace_payload(item) for item in matched])
    except Exception as e:
        raise internal_error(operation="Search session traces", exception=e) from e
