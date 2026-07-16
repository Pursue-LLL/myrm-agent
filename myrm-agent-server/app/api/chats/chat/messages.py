from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    CursorPage,
    MessageResponse,
)
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_helpers import filter_messages
from app.services.chat.chat_service import ChatService

router = APIRouter()


@router.get("/search", response_model=StandardSuccessResponse)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    since: datetime | None = Query(None, description="Only messages after this time (ISO 8601)"),
    until: datetime | None = Query(None, description="Only messages before this time (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Full-text search across all chat messages using FTS5.

    Returns matching messages with highlighted snippets and their parent chat titles.
    Optionally filter by time range using since/until parameters.
    """
    try:
        items, total = await ChatService.search_messages(
            q,
            limit=limit,
            offset=offset,
            since=since,
            until=until,
        )
        return success_response(data={"items": items, "total": total})
    except Exception as e:
        raise internal_error(operation="Search messages", exception=e) from e


@router.get("/{chat_id}/messages", response_model=StandardSuccessResponse)
async def get_chat_messages(
    chat_id: str,
    before: str | None = Query(None, description="Cursor: load messages before this message ID"),
    limit: int = Query(50, ge=1, le=100, description="Messages per page"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Cursor-paginated message loading.

    Returns messages in ascending time order (oldest first).
    Pass ``before`` to load messages older than the given cursor.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        messages, has_more = await ChatService.get_messages_paginated(
            chat_id,
            before=before,
            limit=limit,
        )

        filtered_messages = filter_messages(messages, api_key=None)

        from myrm_agent_harness.utils.text_sanitizer import (
            extract_and_strip_think_blocks,
        )

        items = []
        for msg in filtered_messages:
            content = msg.content
            metadata = msg.extra_data or {}
            if msg.role == "assistant":
                content, think_reasoning = extract_and_strip_think_blocks(content)
                # 优先使用 think blocks 中的 reasoning_content
                if think_reasoning:
                    metadata = dict(metadata)
                    metadata["reasoning_content"] = think_reasoning
                # 否则使用 extra_data["reasoning"]（来自 StreamContentCollector）
                elif metadata.get("reasoning") and not metadata.get("reasoning_content"):
                    metadata = dict(metadata)
                    metadata["reasoning_content"] = metadata.pop("reasoning")

            items.append(
                MessageResponse(
                    messageId=msg.id,
                    chatId=msg.chat_id,
                    role=msg.role,
                    content=content,
                    metadata=metadata,
                    createdAt=msg.created_at,
                    siblingGroupId=msg.sibling_group_id,
                    siblingCount=msg.sibling_count,
                    siblingIndex=msg.sibling_index,
                )
            )

        page = CursorPage(
            messages=items,
            has_more=has_more,
            next_cursor=items[0].messageId if items and has_more else None,
        )

        return success_response(data=page.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get chat messages", exception=e) from e


@router.delete("/{chat_id}/messages", response_model=StandardSuccessResponse)
async def delete_chat_messages(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Intelligent Session Focus & Flush.

    Soft-deletes all messages in the chat session, effectively clearing the LLM's context
    memory, while perfectly preserving the underlying sandbox environment, artifacts,
    and background processes.
    """
    try:
        success = await ChatService.focus_flush_session(chat_id)
        if not success:
            raise not_found_error("Chat session")

        return success_response(data={"cleared": True})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Focus flush messages", exception=e) from e


@router.get("/{chat_id}/export", response_model=StandardSuccessResponse)
async def export_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Export chat metadata, messages, usage summary, tool activity, and agent info for client-side formatting."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        messages = await ChatService.get_all_messages(chat_id)

        filtered_messages = filter_messages(messages, api_key=None)

        from myrm_agent_harness.utils.text_sanitizer import (
            extract_and_strip_think_blocks,
        )

        items = []
        for msg in filtered_messages:
            content = msg.content
            metadata = msg.extra_data or {}
            if msg.role == "assistant":
                content, think_reasoning = extract_and_strip_think_blocks(content)
                if think_reasoning:
                    metadata = dict(metadata)
                    metadata["reasoning_content"] = think_reasoning
                elif metadata.get("reasoning") and not metadata.get("reasoning_content"):
                    metadata = dict(metadata)
                    metadata["reasoning_content"] = metadata.pop("reasoning")

            items.append(
                {
                    "role": msg.role,
                    "content": content,
                    "createdAt": msg.created_at.isoformat(),
                    "metadata": metadata,
                }
            )

        tool_summary = await _build_tool_summary(chat_id, db)
        agent_info = await _build_agent_info(chat.agent_id, db)
        tool_call_details = await _build_tool_call_details(chat_id, db)

        return success_response(
            data={
                "chat": {
                    "id": chat.id,
                    "title": chat.title,
                    "source": chat.source,
                    "createdAt": chat.created_at.isoformat(),
                },
                "messages": items,
                "usageSummary": {
                    "totalCalls": chat.total_calls,
                    "totalTokens": chat.total_tokens,
                    "totalUsd": chat.total_usd,
                },
                "toolSummary": tool_summary,
                "agentInfo": agent_info,
                "toolCallDetails": tool_call_details,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Export chat", exception=e) from e


async def _build_tool_summary(chat_id: str, db: AsyncSession) -> dict[str, object] | None:
    """Aggregate tool call statistics from AgentTurn/AgentEvent tables.

    Returns None when no turn data exists (e.g. sandbox mode where TurnManager is disabled).
    """
    from collections import defaultdict

    from sqlalchemy import select

    from app.database.models.agent_event import AgentEvent, AgentTurn
    from app.services.event.types import EventType

    turn_rows = (await db.execute(select(AgentTurn.id).where(AgentTurn.chat_id == chat_id))).scalars().all()

    if not turn_rows:
        return None

    events = (
        await db.execute(
            select(AgentEvent.tool_name, AgentEvent.duration_ms).where(
                AgentEvent.turn_id.in_(turn_rows),
                AgentEvent.tool_name.isnot(None),
                AgentEvent.event_type == EventType.TOOL_CALL_END.value,
            )
        )
    ).all()

    if not events:
        return None

    tool_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "totalMs": 0})
    total_calls = 0
    total_ms = 0
    for tool_name, duration_ms in events:
        bucket = tool_buckets[tool_name]
        bucket["count"] += 1
        bucket["totalMs"] += duration_ms or 0
        total_calls += 1
        total_ms += duration_ms or 0

    tools_used = sorted(
        [{"name": name, "count": b["count"], "totalMs": b["totalMs"]} for name, b in tool_buckets.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "totalToolCalls": total_calls,
        "totalDurationMs": total_ms,
        "toolsUsed": tools_used,
    }


async def _build_agent_info(agent_id: str | None, db: AsyncSession) -> dict[str, str | None] | None:
    """Fetch Agent identity for export (name, model, description)."""
    if not agent_id:
        return None

    from sqlalchemy import select

    from app.database.models.agent import Agent

    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        return None

    model_name: str | None = None
    if agent.model_selection and isinstance(agent.model_selection, dict):
        model_name = agent.model_selection.get("model")

    return {
        "name": agent.name,
        "model": model_name,
        "description": agent.description or None,
    }


_SENSITIVE_KEY_PATTERN_PARTS = ("key", "secret", "token", "password", "credential", "auth")
_ARG_SUMMARY_MAX_LEN = 200


def _sanitize_args_summary(payload: dict) -> str:
    """Extract a truncated, sanitized summary of tool call arguments from event payload."""
    args = payload.get("arguments") or payload.get("args") or payload.get("input")
    if not args:
        return ""
    if isinstance(args, str):
        text = args
    else:
        parts: list[str] = []
        items = args.items() if isinstance(args, dict) else []
        for k, v in items:
            k_lower = k.lower()
            if any(pat in k_lower for pat in _SENSITIVE_KEY_PATTERN_PARTS):
                parts.append(f"{k}=***")
            else:
                val_str = str(v) if not isinstance(v, str) else v
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                parts.append(f"{k}={val_str}")
        text = ", ".join(parts)

    if len(text) > _ARG_SUMMARY_MAX_LEN:
        return text[: _ARG_SUMMARY_MAX_LEN - 3] + "..."
    return text


async def _build_tool_call_details(chat_id: str, db: AsyncSession) -> list[dict[str, object]] | None:
    """Fetch per-tool-call details ordered by execution sequence."""
    from sqlalchemy import select

    from app.database.models.agent_event import AgentEvent, AgentTurn
    from app.services.event.types import EventType

    turn_rows = (
        await db.execute(
            select(AgentTurn.id, AgentTurn.turn_index)
            .where(AgentTurn.chat_id == chat_id)
            .order_by(AgentTurn.turn_index)
        )
    ).all()

    if not turn_rows:
        return None

    turn_ids = [t[0] for t in turn_rows]

    events = (
        await db.execute(
            select(
                AgentEvent.turn_id,
                AgentEvent.tool_name,
                AgentEvent.payload,
                AgentEvent.duration_ms,
                AgentEvent.event_index,
            )
            .where(
                AgentEvent.turn_id.in_(turn_ids),
                AgentEvent.tool_name.isnot(None),
                AgentEvent.event_type == EventType.TOOL_CALL_END.value,
            )
            .order_by(AgentEvent.event_index)
        )
    ).all()

    if not events:
        return None

    turn_index_map = {t[0]: t[1] for t in turn_rows}

    details: list[dict[str, object]] = []
    for turn_id, tool_name, payload, duration_ms, _event_idx in events:
        details.append({
            "turnIndex": turn_index_map.get(turn_id, 0),
            "name": tool_name,
            "argsSummary": _sanitize_args_summary(payload or {}),
            "durationMs": duration_ms,
        })

    return details
