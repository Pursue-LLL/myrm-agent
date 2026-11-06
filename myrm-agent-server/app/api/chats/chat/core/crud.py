"""[OUTPUT]
- router (POS: sub-router mounted by the core package)

[POS]
Chat core API: chat list/detail, save, delete and batch delete.
"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import ChatCreate, ChatDetail, ChatDetailData, ChatListItem, PaginatedResponse, PaginationMeta
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=50)


@router.get("/", response_model=StandardSuccessResponse)
async def get_chats(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量，1-100"),
    source: str | None = Query(None, description="按来源渠道过滤 (web/telegram/feishu 等)"),
    project_id: str | None = Query(None, description="按项目过滤"),
    unassigned: bool = Query(False, description="仅显示未归属项目的会话"),
    keyword: str | None = Query(None, description="按标题或首条消息模糊搜索"),
    tags: list[str] | None = Query(None, description="按多维度会话标签过滤（如 BugFix, Refactor 等）"),
    match_mode: str = Query("any", description="标签聚合模式 (any: 并集, all: 交集)"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取聊天历史列表（支持分页、来源、项目、关键词及标签过滤）"""
    try:
        chats, total = await ChatService.get_chat_list(
            page,
            page_size,
            source=source,
            project_id=project_id,
            unassigned=unassigned,
            keyword=keyword,
            tags=tags,
            match_mode=match_mode,
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
                tags=chat.tags,
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

        from app.services.chat.effective_workspace import (
            resolve_effective_chat_workspace,
        )

        workspace_dir = await resolve_effective_chat_workspace(
            chat,
            jit_fallback=True,
            persist_jit=True,
        )

        chat_detail = ChatDetail(
            id=chat.id,
            title=chat.title,
            actionMode=chat.action_mode,
            activeMoaPresetId=chat.active_moa_preset_id,
            agent_id=chat.agent_id,
            is_incognito=chat.is_incognito,
            compacted_summary=chat.compacted_summary,
            compacted_before_id=chat.compacted_before_id,
            workspace_dir=workspace_dir,
            session_loaded_skill_names=chat.session_loaded_skill_names,
            session_access_roots=chat.session_access_roots,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

        message_count = await ChatService.count_messages(chat_id)

        from app.services.chat.turn_outline_service import (
            TurnOutlineProjectionService,
        )

        turn_outline = await TurnOutlineProjectionService.get_chat_turn_outline(chat_id)

        data = ChatDetailData(
            chat=chat_detail,
            message_count=message_count,
            turn_outline=turn_outline,
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
