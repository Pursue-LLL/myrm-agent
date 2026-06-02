"""Shared Context history promotion operations.

[INPUT]
app.api.memory.shared_context_schemas (POS: 共享上下文 API Schema 层)
app.services.memory.shared_context::SharedContextService (POS: 共享上下文业务服务)
app.services.memory.shared_context_history::SharedContextHistoryService (POS: 共享上下文历史证据服务)

[OUTPUT]
router: 会话历史搜索和历史消息提升为 Shared Context 写入提案的端点

[POS]
共享上下文历史证据 API 操作层。提供从会话历史检索证据并生成可审批提案的产品入口。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.operations.shared_context_serializers import proposal_to_item
from app.api.memory.shared_context_schemas import (
    CreateSharedContextProposalFromHistoryRequest,
    SharedContextHistoryMessageItem,
    SharedContextHistorySearchRequest,
    SharedContextHistorySearchResponse,
    SharedContextWriteProposalItem,
)
from app.services.memory.shared_context import SharedContextService
from app.services.memory.shared_context_history import (
    SharedContextHistoryHit,
    SharedContextHistoryService,
    build_history_proposal_metadata,
    prepare_history_proposal_content,
)

router = APIRouter(prefix="/shared-contexts")


def _raise_bad_request(exc: ValueError) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _history_hit_to_item(hit: SharedContextHistoryHit) -> SharedContextHistoryMessageItem:
    return SharedContextHistoryMessageItem(
        message_id=hit.message_id,
        chat_id=hit.chat_id,
        role=hit.role,
        content=hit.content,
        snippet=hit.snippet,
        chat_title=hit.chat_title,
        sent_at=hit.sent_at,
    )


@router.post("/{context_id}/history/search", response_model=SharedContextHistorySearchResponse)
async def search_shared_context_history(
    context_id: str,
    body: SharedContextHistorySearchRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextHistorySearchResponse:
    """Search chat history for evidence that can be promoted into a Shared Context proposal."""
    context = await SharedContextService(db).get_context(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")

    hits, total = await SharedContextHistoryService(db).search_messages(
        query=body.query,
        limit=body.limit,
        offset=body.offset,
        since=body.since,
        until=body.until,
    )
    return SharedContextHistorySearchResponse(
        context_id=context_id,
        query=body.query,
        items=[_history_hit_to_item(hit) for hit in hits],
        total=total,
    )


@router.post(
    "/{context_id}/proposals/from-history",
    response_model=SharedContextWriteProposalItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_shared_context_proposal_from_history(
    context_id: str,
    body: CreateSharedContextProposalFromHistoryRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalItem:
    """Promote a selected chat history message into a governed Shared Context write proposal."""
    shared_context_service = SharedContextService(db)
    context = await shared_context_service.get_context(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    if context.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shared context is not active")

    source = await SharedContextHistoryService(db).get_message(body.message_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat history message not found")

    try:
        content, truncated = prepare_history_proposal_content(body.content or source.content)
        metadata = build_history_proposal_metadata(
            source,
            extra_metadata=body.metadata,
            content_truncated=truncated,
        )
        proposal = await shared_context_service.create_write_proposal(
            context_id=context_id,
            memory_type=body.memory_type,
            content=content,
            metadata=metadata,
            source_type="chat_history",
            source_id=source.message_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)

    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    return proposal_to_item(proposal)
