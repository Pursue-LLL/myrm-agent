"""Chat trash (recycle bin) API endpoints.

Soft-deleted chats are moved to trash and can be listed, restored,
permanently deleted, or bulk-emptied.
"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.dto import ChatListItem, PaginatedResponse, PaginationMeta
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter(tags=["chat-trash"])


@router.get("/trash", response_model=StandardSuccessResponse)
async def get_trashed_chats(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    """List all trashed (soft-deleted) chat sessions."""
    try:
        chats, total = await ChatService.get_trashed_chats(page, page_size)
        chat_items = [
            ChatListItem(
                id=chat.id,
                title=chat.title,
                firstMessage=chat.first_message,
                lastMessage=chat.last_message[:100] if chat.last_message else "",
                actionMode=chat.action_mode,
                source=chat.source,
                isCompacted=bool(chat.compacted_summary and chat.compacted_before_id),
                isPinned=False,
                pinOrder=0,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                deletedAt=chat.deleted_at,
            )
            for chat in chats
        ]
        total_pages = ceil(total / page_size) if total > 0 else 1
        return success_response(
            data=PaginatedResponse(
                items=chat_items,
                pagination=PaginationMeta(
                    page=page,
                    page_size=page_size,
                    total=total,
                    total_pages=total_pages,
                    has_next=page < total_pages,
                    has_prev=page > 1,
                ),
            ).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="List trashed chats", exception=e) from e


@router.get("/trash/count", response_model=StandardSuccessResponse)
async def get_trash_count() -> JSONResponse:
    """Return the number of trashed chats (for sidebar badge)."""
    try:
        count = await ChatService.count_trashed_chats()
        return success_response(data={"count": count})
    except Exception as e:
        raise internal_error(operation="Count trashed chats", exception=e) from e


@router.post("/trash/{chat_id}/restore", response_model=StandardSuccessResponse)
async def restore_chat(chat_id: str) -> JSONResponse:
    """Restore a trashed chat back to the active list."""
    try:
        ok = await ChatService.restore_chat(chat_id)
        if not ok:
            raise not_found_error("Trashed chat session")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Restore chat", exception=e) from e


@router.get("/trash/{chat_id}/cascade-info", response_model=StandardSuccessResponse)
async def get_cascade_info(chat_id: str) -> JSONResponse:
    """Return count of derived memories linked to a trashed chat (for deletion preview)."""
    try:
        counts = await ChatService.get_cascade_info(chat_id)
        total = sum(counts.values())
        return success_response(data={"counts": counts, "total": total})
    except Exception as e:
        raise internal_error(operation="Get cascade info", exception=e) from e


@router.delete("/trash/{chat_id}", response_model=StandardSuccessResponse)
async def permanently_delete_chat(chat_id: str) -> JSONResponse:
    """Permanently delete a trashed chat (irreversible), including derived memories."""
    try:
        ok = await ChatService.permanently_delete_chat(chat_id)
        if not ok:
            raise not_found_error("Trashed chat session")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Permanently delete chat", exception=e) from e


@router.delete("/trash", response_model=StandardSuccessResponse)
async def empty_trash() -> JSONResponse:
    """Permanently delete ALL trashed chats (empty recycle bin)."""
    try:
        count = await ChatService.empty_trash()
        return success_response(data={"deleted_count": count})
    except Exception as e:
        raise internal_error(operation="Empty trash", exception=e) from e
