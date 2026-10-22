"""FastAPI router for Planner-Generator-Evaluator Tri-Role Separation Pipeline (Item 40).

[INPUT]
- app.schemas.tri_role::{
    CreateTriRoleSessionRequest,
    PlanSubmissionRequest,
    GenerationSubmissionRequest,
    EvaluateStageRequest,
    RestoreFromManifestRequest,
  }
- app.services.agent.tri_role_service::{
    TriRoleService,
    get_tri_role_service,
  }

[OUTPUT]
- Router mounted under /chats/{chat_id}/tri-role.

[POS]
- HTTP endpoints for cognitive separation pipeline, independent evaluator verdicts,
  and cross-session artifact handoff manifests.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from myrm_agent_harness.agent.coordination.tri_role import TriRolePipelineError

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.tri_role import (
    CreateTriRoleSessionRequest,
    EvaluateStageRequest,
    GenerationSubmissionRequest,
    PlanSubmissionRequest,
    RestoreFromManifestRequest,
)
from app.services.agent.tri_role_service import (
    TriRoleService,
    get_tri_role_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/tri-role", tags=["Tri-Role Separation Pipeline"])


@router.post(
    "/sessions",
    response_model=StandardSuccessResponse,
    summary="Create a new tri-role separation pipeline session",
)
def create_session_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: CreateTriRoleSessionRequest = ...,
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Initialize a multi-agent tri-role pipeline session with discrete stages."""
    try:
        session = service.create_session(req)
        return create_success_response(session.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/sessions",
    response_model=StandardSuccessResponse,
    summary="Get active tri-role session status",
)
def get_session_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Retrieve full status of tri-role pipeline session for current chat."""
    session = service.get_session(chat_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tri-role session for chat '{chat_id}' not found.",
        )
    return create_success_response(session.model_dump())


@router.post(
    "/stages/{stage_id}/plan",
    response_model=StandardSuccessResponse,
    summary="Planner submits horizon breakdown and acceptance criteria",
)
def submit_plan_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    stage_id: str = Path(..., min_length=1, description="Pipeline stage ID"),
    req: PlanSubmissionRequest = ...,
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Record Planner step output and advance stage to GENERATING."""
    try:
        stage = service.submit_plan(session_id=chat_id, stage_id=stage_id, req=req)
        return create_success_response(stage.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/stages/{stage_id}/generate",
    response_model=StandardSuccessResponse,
    summary="Generator submits code deliverables and artifact outputs",
)
def submit_generation_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    stage_id: str = Path(..., min_length=1, description="Pipeline stage ID"),
    req: GenerationSubmissionRequest = ...,
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Record Generator step deliverables and advance stage to EVALUATING."""
    try:
        stage = service.submit_generation(session_id=chat_id, stage_id=stage_id, req=req)
        return create_success_response(stage.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/stages/{stage_id}/evaluate",
    response_model=StandardSuccessResponse,
    summary="Evaluator renders independent adversary verdict on criteria",
)
def evaluate_stage_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    stage_id: str = Path(..., min_length=1, description="Pipeline stage ID"),
    req: EvaluateStageRequest = ...,
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Render independent evaluation score, accepting or rejecting current stage."""
    try:
        verdict = service.evaluate_stage(session_id=chat_id, stage_id=stage_id, req=req)
        return create_success_response(verdict.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/advance",
    response_model=StandardSuccessResponse,
    summary="Advance to next discrete stage upon acceptance",
)
def advance_to_next_stage_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Advance session pointer to the next stage if current stage is accepted."""
    try:
        session = service.advance_to_next_stage(session_id=chat_id)
        return create_success_response(session.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/manifest",
    response_model=StandardSuccessResponse,
    summary="Export cumulative or stage-specific artifact handoff manifest",
)
def export_manifest_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    stage_id: str | None = Query(default=None, description="Optional specific stage ID"),
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Export standardized artifact manifest enabling zero-loss handoff."""
    try:
        manifest = service.export_manifest(session_id=chat_id, stage_id=stage_id)
        return create_success_response(manifest.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/manifest/restore",
    response_model=StandardSuccessResponse,
    summary="Restore execution into a new session from an artifact manifest",
)
def restore_from_manifest_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: RestoreFromManifestRequest = ...,
    service: TriRoleService = Depends(get_tri_role_service),
) -> StandardSuccessResponse:
    """Hydrate new session baseline from prior artifact manifest without context loss."""
    try:
        restored = service.restore_from_manifest(req)
        return create_success_response(restored.model_dump())
    except TriRolePipelineError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
