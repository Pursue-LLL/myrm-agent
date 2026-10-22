# -*- coding: utf-8 -*-
"""FastAPI router for subagent live transcript, persistent delegation ledger, and smart approvals."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.delegation_transcript import (
    ConsumeApprovalResponse,
    CreateDelegationTaskRequest,
    DelegationTaskRecordDTO,
    EmitTranscriptEventRequest,
    EvaluateCommandApprovalRequest,
    MoAReasoningAllocationRequest,
    MoAReasoningAllocationResponse,
    RecoverOrphansResponse,
    ResolveApprovalRequest,
    SaveCheckpointRequest,
    SmartApprovalRequestDTO,
    SmartApprovalResolutionDTO,
    SubagentTranscriptEventDTO,
    UpdateDelegationStatusRequest,
)
from app.services.agent.delegation_transcript_service import (
    DelegationTranscriptService,
    get_delegation_transcript_service,
)

router = APIRouter(prefix="/delegation-transcript", tags=["delegation-transcript"])


@router.post(
    "/tasks",
    response_model=DelegationTaskRecordDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new delegated subagent task in persistent ledger",
)
def create_task(
    req: CreateDelegationTaskRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> DelegationTaskRecordDTO:
    return service.create_task(req)


@router.get(
    "/tasks",
    response_model=list[DelegationTaskRecordDTO],
    summary="List delegated subagent tasks with optional session or status filter",
)
def list_tasks(
    session_id: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> list[DelegationTaskRecordDTO]:
    return service.list_tasks(session_id=session_id, status=task_status)


@router.get(
    "/tasks/{task_id}",
    response_model=DelegationTaskRecordDTO,
    summary="Get delegated task details and execution state",
)
def get_task(
    task_id: str,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> DelegationTaskRecordDTO:
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return task


@router.post(
    "/tasks/{task_id}/status",
    response_model=DelegationTaskRecordDTO,
    summary="Update execution status of a delegated task",
)
def update_task_status(
    task_id: str,
    req: UpdateDelegationStatusRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> DelegationTaskRecordDTO:
    task = service.update_task_status(task_id, req)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return task


@router.post(
    "/tasks/{task_id}/checkpoint",
    response_model=DelegationTaskRecordDTO,
    summary="Record task progress checkpoint and generated artifacts",
)
def save_checkpoint(
    task_id: str,
    req: SaveCheckpointRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> DelegationTaskRecordDTO:
    task = service.save_checkpoint(task_id, req)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return task


@router.post(
    "/tasks/{task_id}/events",
    response_model=SubagentTranscriptEventDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Emit live transcript event for human-readable streaming",
)
def emit_event(
    task_id: str,
    req: EmitTranscriptEventRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> SubagentTranscriptEventDTO:
    return service.emit_event(task_id, req)


@router.get(
    "/tasks/{task_id}/events",
    response_model=list[SubagentTranscriptEventDTO],
    summary="Get live transcript events for a delegated task",
)
def get_events(
    task_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1),
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> list[SubagentTranscriptEventDTO]:
    return service.get_events(task_id, after_seq=after_seq, limit=limit)


@router.post(
    "/approvals/evaluate",
    response_model=SmartApprovalRequestDTO,
    summary="Evaluate command risk and create single-use approval request",
)
def evaluate_command(
    req: EvaluateCommandApprovalRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> SmartApprovalRequestDTO:
    return service.evaluate_command(req)


@router.post(
    "/approvals/{approval_id}/resolve",
    response_model=SmartApprovalResolutionDTO,
    summary="Resolve smart approval with optional interactive /deny feedback",
)
def resolve_approval(
    approval_id: str,
    req: ResolveApprovalRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> SmartApprovalResolutionDTO:
    res = service.resolve_approval(approval_id, req)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found.",
        )
    return res


@router.post(
    "/approvals/{approval_id}/consume",
    response_model=ConsumeApprovalResponse,
    summary="Consume single-use approval token before execution",
)
def consume_approval(
    approval_id: str,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> ConsumeApprovalResponse:
    return service.consume_approval(approval_id)


@router.post(
    "/ledger/recover",
    response_model=RecoverOrphansResponse,
    summary="Trigger persistent ledger orphan recovery for crash resilience",
)
def recover_orphans(
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> RecoverOrphansResponse:
    return service.recover_orphans()


@router.post(
    "/reasoning/allocate",
    response_model=MoAReasoningAllocationResponse,
    summary="Allocate MoA dynamic reasoning effort and token budget by role",
)
def allocate_reasoning(
    req: MoAReasoningAllocationRequest,
    service: DelegationTranscriptService = Depends(get_delegation_transcript_service),
) -> MoAReasoningAllocationResponse:
    return service.allocate_reasoning(req)
