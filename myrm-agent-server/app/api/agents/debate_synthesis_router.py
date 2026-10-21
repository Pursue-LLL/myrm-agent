"""[INPUT] chat_id, workflow_id, request bodies from schemas/debate_synthesis.py.
[OUTPUT] StandardSuccessResponse containing SynthesisWorkflowResponse or TradeoffMatrixDTO.
[POS] FastAPI router for Hierarchical Leader-Worker Debate & Synthesis Pattern endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.debate_synthesis import (
    AutoDecomposeRequest,
    CreateSynthesisWorkflowRequest,
    SubmitProposalRequest,
    SynthesizeMatrixRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.debate_synthesis_service import DebateSynthesisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/debate-synthesis", tags=["Debate Synthesis Pattern"])


def get_debate_synthesis_service() -> DebateSynthesisService:
    """Dependency injector for DebateSynthesisService singleton."""
    return DebateSynthesisService.get_instance()


@router.post(
    "",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a hierarchical debate synthesis consulting workflow",
)
def create_synthesis_workflow_endpoint(
    chat_id: str,
    req: CreateSynthesisWorkflowRequest,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Initialize a 3-stage Leader-Worker consulting workflow."""
    workflow = service.create_workflow(chat_id=chat_id, req=req)
    return create_success_response(data=workflow)


@router.get(
    "",
    response_model=StandardSuccessResponse,
    summary="List all synthesis workflows for a chat",
)
def list_synthesis_workflows_endpoint(
    chat_id: str,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """List active and completed synthesis workflows for the given chat session."""
    workflows = service.list_workflows(chat_id=chat_id)
    return create_success_response(data=workflows)


@router.get(
    "/{workflow_id}",
    response_model=StandardSuccessResponse,
    summary="Get synthesis workflow state",
)
def get_synthesis_workflow_endpoint(
    chat_id: str,
    workflow_id: str,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Fetch complete workflow snapshot including subtasks, proposals, and matrix."""
    workflow = service.get_workflow(workflow_id)
    if not workflow or workflow.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found in chat {chat_id}",
        )
    return create_success_response(data=workflow)


@router.post(
    "/{workflow_id}/decompose",
    response_model=StandardSuccessResponse,
    summary="Leader derives subtask DAG with explicit dependencies",
)
def auto_decompose_endpoint(
    chat_id: str,
    workflow_id: str,
    req: AutoDecomposeRequest,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Leader coordinator automatically derives research and audit subtasks."""
    workflow = service.get_workflow(workflow_id)
    if not workflow or workflow.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    try:
        updated = service.auto_decompose(
            workflow_id=workflow_id,
            leader_agent_id=req.leader_agent_id,
        )
        return create_success_response(data=updated)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{workflow_id}/proposals",
    response_model=StandardSuccessResponse,
    summary="Submit a candidate proposal by analyst or auditor",
)
def submit_proposal_endpoint(
    chat_id: str,
    workflow_id: str,
    req: SubmitProposalRequest,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Record a specialist solution proposal and advance workflow lifecycle."""
    workflow = service.get_workflow(workflow_id)
    if not workflow or workflow.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    updated = service.submit_proposal(workflow_id=workflow_id, req=req)
    return create_success_response(data=updated)


@router.post(
    "/{workflow_id}/advance-debate",
    response_model=StandardSuccessResponse,
    summary="Advance cross-examination debate round",
)
def advance_cross_debate_endpoint(
    chat_id: str,
    workflow_id: str,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Progress cross debate round with automatic convergence guard."""
    workflow = service.get_workflow(workflow_id)
    if not workflow or workflow.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    updated = service.advance_cross_debate(workflow_id)
    return create_success_response(data=updated)


@router.post(
    "/{workflow_id}/synthesize",
    response_model=StandardSuccessResponse,
    summary="Synthesize multi-dimensional decision trade-off matrix",
)
def synthesize_decision_matrix_endpoint(
    chat_id: str,
    workflow_id: str,
    req: SynthesizeMatrixRequest,
    service: DebateSynthesisService = Depends(get_debate_synthesis_service),
) -> StandardSuccessResponse:
    """Leader synthesizes the Trade-off Matrix and selects optimal proposal."""
    workflow = service.get_workflow(workflow_id)
    if not workflow or workflow.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    try:
        matrix = service.synthesize_decision_matrix(workflow_id=workflow_id, req=req)
        return create_success_response(data=matrix)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
