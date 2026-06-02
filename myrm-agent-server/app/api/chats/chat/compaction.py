from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    UpdateSummaryRequest,
)
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


class CompactRequest(BaseModel):
    focus_topic: str = Field(default="", max_length=200)


@router.post("/{chat_id}/compact", response_model=StandardSuccessResponse)
async def compact_chat(
    chat_id: str,
    body: CompactRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Compact chat context by generating a persistent summary.

    Original messages are preserved — the summary is used by the Agent
    layer to reduce token cost on subsequent interactions.
    """
    from app.services.chat.compact_service import compact_chat as do_compact

    focus_topic = body.focus_topic.strip() if body and body.focus_topic else ""

    try:
        result = await do_compact(db, chat_id, focus_topic=focus_topic)
        return success_response(
            data={
                "compacted": result.compacted,
                "original_tokens": result.original_tokens,
                "summary_tokens": result.summary_tokens,
                "tokens_saved": result.tokens_saved,
                "message_count": result.message_count,
                "backup_path": result.backup_path,
                "reason": result.reason,
                "focus_topic": focus_topic,
            }
        )
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Compact chat context", exception=e) from e

@router.put("/{chat_id}/compaction/summary", response_model=StandardSuccessResponse)
async def update_compaction_summary(
    chat_id: str,
    body: UpdateSummaryRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update compaction summary for a chat session (admin override API)."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        await ChatService.update_compaction_summary(chat_id, body.summary)
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update compaction summary", exception=e) from e

@router.get("/{chat_id}/archive", response_model=StandardSuccessResponse)
async def get_chat_archive(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Retrieve archived messages from compacted history (read-only, does not affect prefix cache)."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        from app.services.chat.compact_service import get_archived_messages

        messages = await get_archived_messages(chat_id)
        return success_response(data={"messages": messages})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get chat archive", exception=e) from e

