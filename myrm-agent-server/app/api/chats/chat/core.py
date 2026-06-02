from __future__ import annotations

import os
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    ChatCreate,
    ChatDetail,
    ChatDetailData,
    ChatListItem,
    PaginatedResponse,
    PaginationMeta,
)
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

router = APIRouter()


@router.get("/", response_model=StandardSuccessResponse)
async def get_chats(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量，1-100"),
    source: str | None = Query(None, description="按来源渠道过滤 (web/telegram/feishu 等)"),
    project_id: str | None = Query(None, description="按项目过滤"),
    unassigned: bool = Query(False, description="仅显示未归属项目的会话"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取聊天历史列表（支持分页、来源和项目过滤）"""
    try:
        chats, total = await ChatService.get_chat_list(
            page, page_size, source=source, project_id=project_id, unassigned=unassigned,
        )

        chat_items = [
            ChatListItem(
                id=chat.id,
                title=chat.title,
                firstMessage=chat.first_message,
                lastMessage=chat.last_message[:100] if chat.last_message else "",
                actionMode=chat.action_mode,
                source=chat.source,
                isCompacted=bool(chat.compacted_summary and chat.compacted_before_id),
                isPinned=chat.is_pinned,
                pinOrder=chat.pin_order,
                projectId=chat.project_id,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
            for chat in chats
        ]

        # 计算分页信息
        total_pages = ceil(total / page_size) if total > 0 else 1
        pagination_meta = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

        paginated_data = PaginatedResponse[ChatListItem](items=chat_items, pagination=pagination_meta)

        return success_response(data=paginated_data.model_dump())
    except Exception as e:
        raise internal_error(operation="Get chat list", exception=e) from e


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
                "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
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


@router.get("/{chat_id}", response_model=StandardSuccessResponse)
async def get_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取聊天元数据（不含消息，消息通过分页端点加载）"""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        workspace_dir = chat.workspace_dir
        if not workspace_dir:
            workspace_dir = await ChatService.ensure_default_workspace_dir(chat_id)

        chat_detail = ChatDetail(
            id=chat.id,
            title=chat.title,
            actionMode=chat.action_mode,
            compacted_summary=chat.compacted_summary,
            compacted_before_id=chat.compacted_before_id,
            workspace_dir=workspace_dir,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

        message_count = await ChatService.count_messages(chat_id)

        data = ChatDetailData(
            chat=chat_detail,
            message_count=message_count,
        )

        return success_response(data=data.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get chat details", exception=e) from e


@router.post("/", response_model=StandardSuccessResponse)
async def save_chat(
    chat_data: ChatCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """保存聊天会话"""
    if not chat_data.chat_id.strip():
        raise validation_error("Chat ID cannot be empty")

    if chat_data.title and len(chat_data.title) > 500:
        raise validation_error("Title length cannot exceed 500 characters")

    try:
        await ChatService.create_or_update_chat(chat_data)
        return success_response()
    except PermissionError as e:
        raise not_found_error("Chat session") from e
    except ValueError as e:
        # 处理业务逻辑错误（如重复messageId）
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Save chat session", exception=e) from e


@router.delete("/{chat_id}", response_model=StandardSuccessResponse)
async def delete_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """删除聊天会话"""
    if not chat_id.strip():
        raise validation_error("Chat ID cannot be empty")

    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        success = await ChatService.delete_chat(chat_id)
        if not success:
            raise not_found_error("Chat session")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Delete chat session", exception=e) from e


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=50)


@router.post("/batch-delete", response_model=StandardSuccessResponse)
async def batch_delete_chats(body: BatchDeleteRequest) -> JSONResponse:
    """Batch soft-delete multiple chat sessions (move to trash)."""
    try:
        result = await ChatService.batch_delete(body.ids)
        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Batch delete chat sessions", exception=e) from e


MAX_PINNED_CHATS = 9


class PinReorderItem(BaseModel):
    id: str
    pin_order: int = Field(..., ge=1, le=MAX_PINNED_CHATS)


class PinReorderRequest(BaseModel):
    items: list[PinReorderItem] = Field(..., min_length=1, max_length=MAX_PINNED_CHATS)


@router.patch("/{chat_id}/pin", response_model=StandardSuccessResponse)
async def pin_chat(
    chat_id: str,
) -> JSONResponse:
    """Pin a chat to the sidebar top (max 9)."""
    try:
        result = await ChatService.pin_chat(chat_id)
        return success_response(data={"isPinned": result.is_pinned, "pinOrder": result.pin_order})
    except ValueError as e:
        raise validation_error(str(e)) from e
    except LookupError as e:
        raise not_found_error("Chat session") from e
    except Exception as e:
        raise internal_error(operation="Pin chat", exception=e) from e


@router.patch("/{chat_id}/unpin", response_model=StandardSuccessResponse)
async def unpin_chat(
    chat_id: str,
) -> JSONResponse:
    """Unpin a chat from the sidebar top."""
    try:
        await ChatService.unpin_chat(chat_id)
        return success_response(data={"isPinned": False, "pinOrder": 0})
    except LookupError as e:
        raise not_found_error("Chat session") from e
    except Exception as e:
        raise internal_error(operation="Unpin chat", exception=e) from e


@router.put("/pin-reorder", response_model=StandardSuccessResponse)
async def reorder_pinned_chats(
    body: PinReorderRequest,
) -> JSONResponse:
    """Batch reorder pinned chats (after drag-and-drop)."""
    try:
        await ChatService.reorder_pinned_chats([(item.id, item.pin_order) for item in body.items])
        return success_response()
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Reorder pinned chats", exception=e) from e


class UpdateWorkspaceDirRequest(BaseModel):
    """Request to set or clear per-chat working directory."""

    workspace_dir: str | None = Field(None, description="Absolute path or null to clear", max_length=1024)


class RecallExclusionRequest(BaseModel):
    """Request to include or exclude a chat from Conversation Recall."""

    excluded: bool = Field(True, description="Whether this chat should be excluded from Conversation Recall")


@router.patch("/{chat_id}/workspace", response_model=StandardSuccessResponse)
async def update_chat_workspace_dir(
    chat_id: str,
    body: UpdateWorkspaceDirRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Set or clear the per-chat working directory."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        workspace_dir = body.workspace_dir
        if workspace_dir is not None:
            workspace_dir = workspace_dir.strip()
            if not workspace_dir:
                workspace_dir = None
            else:
                from myrm_agent_harness.agent.security.path_security import is_dangerous_path

                resolved = os.path.realpath(os.path.expanduser(workspace_dir))
                if is_dangerous_path(resolved):
                    raise validation_error(f"Path is not allowed as workspace: {workspace_dir}")
                if not os.path.isdir(resolved):
                    raise validation_error(f"Path does not exist or is not a directory: {workspace_dir}")
                workspace_dir = resolved

        await ChatService.update_chat_fields(chat_id, {"workspace_dir": workspace_dir})
        return success_response(data={"workspace_dir": workspace_dir})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update chat workspace directory", exception=e) from e


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

        from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

        from app.database.connection import get_session
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        kind = MemoryOperationKind.FORGET if body.excluded else MemoryOperationKind.WRITE
        summary = (
            "Conversation excluded from recall."
            if body.excluded
            else "Conversation restored to recall."
        )
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
