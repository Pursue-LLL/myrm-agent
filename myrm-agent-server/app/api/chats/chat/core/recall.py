"""[OUTPUT]
- router (POS: sub-router mounted by the core package)

[POS]
Chat core API: conversation recall search/entries and per-chat recall exclusion.
"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.dto import PaginationMeta
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

router = APIRouter()


class RecallExclusionRequest(BaseModel):
    """Request to include or exclude a chat from Conversation Recall."""

    excluded: bool = Field(
        True,
        description="Whether this chat should be excluded from Conversation Recall",
    )


@router.get("/recall/search", response_model=StandardSuccessResponse)
async def search_citable_conversations(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    exclude_chat_id: str | None = Query(None, description="Exclude current chat from results"),
) -> JSONResponse:
    """Search conversation recall index for GUI @chat: citation (SSOT with inject path)."""
    try:
        items, total = await ConversationRecallIndexService.search_citable_chats(
            q,
            limit=limit,
            offset=offset,
            exclude_chat_id=exclude_chat_id,
        )
        return success_response(data={"items": items, "total": total})
    except Exception as e:
        raise internal_error(operation="Search citable conversations", exception=e) from e


@router.get("/recall/entries", response_model=StandardSuccessResponse)
async def list_conversation_recall_entries(
    excluded: bool | None = Query(None, description="Filter by Conversation Recall exclusion state"),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，1-100"),
) -> JSONResponse:
    """List Conversation Recall indexed conversations for management UI."""
    try:
        rows, total = await ConversationRecallIndexService.list_documents(
            excluded=excluded,
            page=page,
            page_size=page_size,
        )
        items = [
            {
                "chat_id": row.chat_id,
                "title": row.title,
                "agent_id": row.agent_id,
                "source": row.source,
                "snippet": row.snippet,
                "summary": row.summary,
                "last_message_at": (row.last_message_at.isoformat() if row.last_message_at else None),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "is_excluded": row.is_excluded,
            }
            for row in rows
        ]
        total_pages = ceil(total / page_size) if total > 0 else 1
        pagination = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
        return success_response(data={"items": items, "pagination": pagination.model_dump()})
    except Exception as e:
        raise internal_error(operation="List conversation recall entries", exception=e) from e


@router.patch("/{chat_id}/recall-exclusion", response_model=StandardSuccessResponse)
async def update_chat_recall_exclusion(
    chat_id: str,
    body: RecallExclusionRequest,
) -> JSONResponse:
    """Exclude or include a chat in Conversation Recall without deleting the chat."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")
        updated = await ConversationRecallIndexService.set_chat_excluded(chat_id, body.excluded)
        if not updated:
            raise not_found_error("Chat session")

        from myrm_agent_harness.toolkits.memory import (
            MemoryOperationKind,
            MemoryOperationStatus,
        )

        from app.database.connection import get_session
        from app.services.memory.ledger.operation_ledger import (
            MemoryOperationLedgerService,
        )

        kind = MemoryOperationKind.FORGET if body.excluded else MemoryOperationKind.WRITE
        summary = "Conversation excluded from recall." if body.excluded else "Conversation restored to recall."
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=kind,
                status=MemoryOperationStatus.SUCCESS,
                summary=summary,
                source="chat_recall_api",
                target_kind="conversation",
                target_id=chat_id,
                metadata={"excluded": body.excluded},
                commit=True,
            )

        return success_response(data={"excluded": body.excluded})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update chat recall exclusion", exception=e) from e
