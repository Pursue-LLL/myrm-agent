from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chats.chat.export_helpers import (
    build_agent_info,
    build_tool_call_details,
    build_tool_summary,
    redact_export_payload,
)
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    CursorPage,
    MessageResponse,
)
from app.schemas.responses import StandardSuccessResponse
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
    redact_secrets: bool = Query(True, description="Whether to redact sensitive secrets and API keys"),
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

        tool_summary = await build_tool_summary(chat_id, db)
        agent_info = await build_agent_info(chat.agent_id, db)
        tool_call_details = await build_tool_call_details(chat_id, db)

        payload_data: dict[str, object] = {
            "chat": {"id": chat.id, "title": chat.title, "source": chat.source, "createdAt": chat.created_at.isoformat()},
            "messages": items,
            "usageSummary": {"totalCalls": chat.total_calls, "totalTokens": chat.total_tokens, "totalUsd": chat.total_usd},
            "toolSummary": tool_summary,
            "agentInfo": agent_info,
            "toolCallDetails": tool_call_details,
            "redacted": redact_secrets,
        }

        if redact_secrets:
            payload_data = redact_export_payload(payload_data)

        return success_response(data=payload_data)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Export chat", exception=e) from e
