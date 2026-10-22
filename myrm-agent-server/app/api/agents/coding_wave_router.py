"""FastAPI router for Coding Agent Wave Preset Pipeline (Item 45).

[INPUT]
- app.schemas.coding_wave::{
    CreateWaveSessionRequest,
    UpdateWaveTaskRequest,
  }
- app.services.agent.coding_wave_service::{
    CodingWaveService,
    get_coding_wave_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/coding-wave and /agents/coding-wave
  for wave session initialization, task updates, strict stage gate advancement,
  and orchestration progress JSON export.

[POS]
- HTTP API layer for optional full-stack coding wave pipeline.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from myrm_agent_harness.agent.coordination.wave_orchestrator import (
    CodingWaveError,
    CodingWaveGateError,
)

from app.schemas.coding_wave import (
    CreateWaveSessionRequest,
    UpdateWaveTaskRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.coding_wave_service import (
    CodingWaveService,
    get_coding_wave_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Coding Agent Wave Pipeline"])


@router.post(
    "/chats/{chat_id}/coding-wave/sessions",
    response_model=StandardSuccessResponse,
    summary="Initialize or reset coding wave session for chat",
)
def create_wave_session_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: CreateWaveSessionRequest = ...,
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> StandardSuccessResponse:
    """Initialize a multi-wave software engineering pipeline with multi-model role assignments."""
    try:
        progress = service.create_wave_session(
            session_id=chat_id,
            preset_dto=req.preset,
            custom_tasks_dto=req.custom_tasks,
        )
        return create_success_response(progress.model_dump())
    except CodingWaveError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/chats/{chat_id}/coding-wave/progress",
    response_model=StandardSuccessResponse,
    summary="Get current wave execution progress for chat session",
)
def get_wave_progress_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> StandardSuccessResponse:
    """Retrieve active stage, tasks list, and completion status of the coding wave."""
    progress = service.get_progress(session_id=chat_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wave session for chat '{chat_id}' not found.",
        )
    return create_success_response(progress.model_dump())


@router.post(
    "/chats/{chat_id}/coding-wave/tasks/update",
    response_model=StandardSuccessResponse,
    summary="Update status and output summary of a task node",
)
def update_wave_task_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: UpdateWaveTaskRequest = ...,
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> StandardSuccessResponse:
    """Update execution state (e.g. COMPLETED) and output summary of an individual wave subtask."""
    try:
        node = service.update_task_status(
            session_id=chat_id,
            task_id=req.task_id,
            status=req.status,
            output_summary=req.output_summary,
        )
        return create_success_response(node.model_dump())
    except CodingWaveError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/chats/{chat_id}/coding-wave/advance",
    response_model=StandardSuccessResponse,
    summary="Advance to next wave stage through strict stage gate",
)
def advance_wave_stage_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> StandardSuccessResponse:
    """Verify that all tasks in the current wave are completed before transitioning to the next stage."""
    try:
        progress = service.advance_stage(session_id=chat_id)
        return create_success_response(progress.model_dump())
    except CodingWaveGateError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    except CodingWaveError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/chats/{chat_id}/coding-wave/export-json",
    summary="Export orchestration_progress.json format",
)
def export_progress_json_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> Response:
    """Export formatted orchestration_progress.json artifact for audit or handoff."""
    try:
        raw_json = service.export_progress_json(session_id=chat_id)
        return Response(content=raw_json, media_type="application/json")
    except CodingWaveError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.get(
    "/agents/coding-wave/preset",
    response_model=StandardSuccessResponse,
    summary="Get default full-stack development wave preset specification",
)
def get_default_preset_endpoint(
    service: CodingWaveService = Depends(get_coding_wave_service),
) -> StandardSuccessResponse:
    """Retrieve official full-stack development wave preset with multi-model role routing."""
    preset = service.get_default_preset()
    return create_success_response(preset.model_dump())
