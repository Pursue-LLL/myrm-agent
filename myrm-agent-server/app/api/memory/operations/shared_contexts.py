"""Shared Context memory operations.

[INPUT]
app.core.utils.errors::handle_llm_exception (POS: 核心错误处理模块)
app.api.memory.shared_context_schemas (POS: 共享上下文 API Schema 层)
app.services.memory.shared_context::SharedContextService (POS: 共享上下文业务服务)
app.services.memory.shared_context_materializer::SharedContextProposalMaterializer (POS: 共享上下文写入物化服务)

[OUTPUT]
router: 共享上下文 CRUD、绑定管理和写入提案审批端点

[POS]
共享上下文 API 操作层。提供产品层共享记忆空间治理，不暴露 team memory 语义。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.operations.shared_context_serializers import binding_to_item, context_to_item, proposal_to_item
from app.api.memory.shared_context_schemas import (
    CreateSharedContextBindingRequest,
    CreateSharedContextRequest,
    CreateSharedContextWriteProposalRequest,
    SharedContextBindingItem,
    SharedContextBindingListResponse,
    SharedContextItem,
    SharedContextListResponse,
    SharedContextProposalStatus,
    SharedContextStatus,
    SharedContextTargetType,
    SharedContextWriteProposalItem,
    SharedContextWriteProposalListResponse,
    UpdateSharedContextRequest,
    UpdateSharedContextWriteProposalRequest,
)
from app.core.utils.errors import handle_llm_exception
from app.services.memory.operation_ledger import MemoryOperationLedgerService
from app.services.memory.shared_context import (
    SharedContextService,
)
from app.services.memory.shared_context_materializer import SharedContextProposalMaterializer

router = APIRouter(prefix="/shared-contexts")


def _raise_bad_request(exc: ValueError) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _record_shared_context_event(
    db: AsyncSession,
    *,
    kind: MemoryOperationKind,
    proposal_id: str,
    memory_type: str | None,
    summary: str,
) -> None:
    await MemoryOperationLedgerService(db).record_event(
        kind=kind,
        status=MemoryOperationStatus.SUCCESS,
        summary=summary,
        memory_id=proposal_id,
        memory_type=memory_type,
        source="shared_context_api",
        target_kind="shared_context_proposal",
        target_id=proposal_id,
        commit=True,
    )


async def _list_shared_contexts_impl(
    status_filter: SharedContextStatus | None,
    db: AsyncSession,
) -> SharedContextListResponse:
    contexts = await SharedContextService(db).list_contexts(status=status_filter)
    items = [context_to_item(context) for context in contexts]
    return SharedContextListResponse(items=items, total=len(items))


async def _create_shared_context_impl(
    body: CreateSharedContextRequest,
    db: AsyncSession,
) -> SharedContextItem:
    try:
        context = await SharedContextService(db).create_context(
            name=body.name,
            description=body.description,
            policy=body.policy,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    return context_to_item(context)


@router.get("/", response_model=SharedContextListResponse)
async def list_shared_contexts(
    status_filter: SharedContextStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextListResponse:
    """List product-level shared contexts."""
    return await _list_shared_contexts_impl(status_filter, db)


@router.get("", response_model=SharedContextListResponse, include_in_schema=False)
async def list_shared_contexts_no_trailing_slash(
    status_filter: SharedContextStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextListResponse:
    """Same as list_shared_contexts; exposed for clients redirected without a trailing slash.

    Next.js dev rewrites issue HTTP 308 from ``.../shared-contexts/`` to ``.../shared-contexts``;
    fetch follows with the same method, so the backend must accept the no-slash collection path.
    """
    return await _list_shared_contexts_impl(status_filter, db)


@router.post("/", response_model=SharedContextItem, status_code=status.HTTP_201_CREATED)
async def create_shared_context(
    body: CreateSharedContextRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextItem:
    """Create a shared memory context."""
    return await _create_shared_context_impl(body, db)


@router.post("", response_model=SharedContextItem, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_shared_context_no_trailing_slash(
    body: CreateSharedContextRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextItem:
    """Same as create_shared_context; see list_shared_contexts_no_trailing_slash."""
    return await _create_shared_context_impl(body, db)


@router.get("/bindings/targets/{target_type}/{target_id}", response_model=SharedContextBindingListResponse)
async def list_shared_context_bindings_for_target(
    target_type: SharedContextTargetType,
    target_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextBindingListResponse:
    """List shared context bindings attached to one runtime target."""
    try:
        bindings = await SharedContextService(db).list_bindings_for_target(
            target_type=target_type,
            target_id=target_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    items = [binding_to_item(binding) for binding in bindings]
    return SharedContextBindingListResponse(items=items, total=len(items))


@router.get("/{context_id}", response_model=SharedContextItem)
async def get_shared_context(
    context_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextItem:
    """Get a shared context by ID."""
    context = await SharedContextService(db).get_context(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    return context_to_item(context)


@router.patch("/{context_id}", response_model=SharedContextItem)
async def update_shared_context(
    context_id: str,
    body: UpdateSharedContextRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextItem:
    """Update a shared context."""
    try:
        context = await SharedContextService(db).update_context(
            context_id,
            name=body.name,
            description=body.description,
            status=body.status,
            policy=body.policy,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    return context_to_item(context)


@router.delete("/{context_id}", response_model=SharedContextItem)
async def archive_shared_context(
    context_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextItem:
    """Archive a shared context without deleting stored memories."""
    context = await SharedContextService(db).archive_context(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    await MemoryOperationLedgerService(db).record_event(
        kind=MemoryOperationKind.FORGET,
        status=MemoryOperationStatus.SUCCESS,
        summary="Shared context archived.",
        memory_id=context_id,
        memory_type="shared_context",
        source="shared_context_api",
        target_kind="shared_context",
        target_id=context_id,
        metadata={"name": context.name},
    )
    return context_to_item(context)


@router.get("/{context_id}/bindings", response_model=SharedContextBindingListResponse)
async def list_shared_context_bindings(
    context_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextBindingListResponse:
    """List bindings for a shared context."""
    service = SharedContextService(db)
    if await service.get_context(context_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    bindings = await service.list_bindings(context_id)
    items = [binding_to_item(binding) for binding in bindings]
    return SharedContextBindingListResponse(items=items, total=len(items))


@router.post("/{context_id}/bindings", response_model=SharedContextBindingItem, status_code=status.HTTP_201_CREATED)
async def create_shared_context_binding(
    context_id: str,
    body: CreateSharedContextBindingRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextBindingItem:
    """Bind a shared context to an agent, channel, cron job, conversation, or task."""
    try:
        binding = await SharedContextService(db).bind_context(
            context_id=context_id,
            target_type=body.target_type,
            target_id=body.target_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    return binding_to_item(binding)


@router.delete("/{context_id}/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shared_context_binding(
    context_id: str,
    binding_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove a shared context binding."""
    deleted = await SharedContextService(db).unbind_context(context_id=context_id, binding_id=binding_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context binding not found")
    await MemoryOperationLedgerService(db).record_event(
        kind=MemoryOperationKind.WRITE,
        status=MemoryOperationStatus.SUCCESS,
        summary="Shared context binding removed.",
        memory_id=context_id,
        memory_type="shared_context",
        source="shared_context_api",
        target_kind="shared_context_binding",
        target_id=binding_id,
    )


@router.get("/{context_id}/proposals", response_model=SharedContextWriteProposalListResponse)
async def list_shared_context_write_proposals(
    context_id: str,
    proposal_status: SharedContextProposalStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalListResponse:
    """List write proposals for a shared context."""
    service = SharedContextService(db)
    if await service.get_context(context_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    proposals = await service.list_write_proposals(context_id=context_id, status=proposal_status, limit=limit)
    items = [proposal_to_item(proposal) for proposal in proposals]
    return SharedContextWriteProposalListResponse(items=items, total=len(items))


@router.post(
    "/{context_id}/proposals",
    response_model=SharedContextWriteProposalItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_shared_context_write_proposal(
    context_id: str,
    body: CreateSharedContextWriteProposalRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalItem:
    """Create a write proposal for a shared context."""
    try:
        proposal = await SharedContextService(db).create_write_proposal(
            context_id=context_id,
            memory_type=body.memory_type,
            content=body.content,
            metadata=body.metadata,
            source_type=body.source_type,
            source_id=body.source_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context not found")
    return proposal_to_item(proposal)


@router.patch("/proposals/{proposal_id}", response_model=SharedContextWriteProposalItem)
async def update_shared_context_write_proposal(
    proposal_id: str,
    body: UpdateSharedContextWriteProposalRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalItem:
    """Edit a pending write proposal before approval."""
    try:
        proposal = await SharedContextService(db).update_write_proposal(
            proposal_id,
            content=body.content,
            metadata=body.metadata,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context write proposal not found")
    await _record_shared_context_event(
        db,
        kind=MemoryOperationKind.WRITE,
        proposal_id=proposal_id,
        memory_type=proposal.memory_type,
        summary="Shared context proposal edited.",
    )
    return proposal_to_item(proposal)


@router.post("/proposals/{proposal_id}/approve", response_model=SharedContextWriteProposalItem)
async def approve_shared_context_write_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalItem:
    """Approve a write proposal and persist it into the target shared namespace."""
    try:
        proposal = await SharedContextProposalMaterializer(db).approve_write_proposal(proposal_id)
    except ValueError as exc:
        _raise_bad_request(exc)
    except Exception as exc:
        handle_llm_exception(exc, "Shared Context proposal materialization")
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context write proposal not found")
    await _record_shared_context_event(
        db,
        kind=MemoryOperationKind.APPROVE,
        proposal_id=proposal_id,
        memory_type=proposal.memory_type,
        summary="Shared context proposal approved and materialized.",
    )
    return proposal_to_item(proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=SharedContextWriteProposalItem)
async def reject_shared_context_write_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SharedContextWriteProposalItem:
    """Reject a write proposal without writing memory."""
    service = SharedContextService(db)
    proposal = await service.get_write_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context write proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shared context write proposal is not pending")
    updated = await service.set_write_proposal_status(proposal_id, "rejected")
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context write proposal not found")
    await _record_shared_context_event(
        db,
        kind=MemoryOperationKind.REJECT,
        proposal_id=proposal_id,
        memory_type=updated.memory_type,
        summary="Shared context proposal rejected.",
    )
    return proposal_to_item(updated)
