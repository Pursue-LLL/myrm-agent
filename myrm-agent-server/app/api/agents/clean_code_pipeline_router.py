"""FastAPI router for Clean-Code Assembly Pipeline and Architecture Dependency Linter (Item 62).

[INPUT]
- app.schemas.clean_code_pipeline::{
    CreateCleanCodeTaskRequest, AdvanceStageRequest, LinterCheckRequest,
  }
- app.services.agent.clean_code_pipeline_service::CleanCodePipelineService

[OUTPUT]
- REST endpoints under /agents/clean-code for 5-stage pipeline and AST architecture linting.

[POS]
- HTTP API layer for Item 62 Clean-Code assembly pipeline.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.clean_code_pipeline import (
    AdvanceStageRequest,
    CreateCleanCodeTaskRequest,
    LinterCheckRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.clean_code_pipeline_service import CleanCodePipelineService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/clean-code",
    tags=["Clean-Code Assembly Pipeline & Architecture Linter"],
)


@router.post(
    "/tasks",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Create and start a 5-stage Clean-Code assembly pipeline",
)
async def create_task(req: CreateCleanCodeTaskRequest) -> StandardSuccessResponse:
    """Create a new clean-code assembly pipeline starting at the Specifier stage."""
    try:
        task_dto = CleanCodePipelineService.create_task(req)
        return create_success_response(data=task_dto.model_dump())
    except Exception as exc:
        logger.exception("Failed to create clean-code task: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/tasks/{task_id}/advance",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Advance the clean-code assembly pipeline to the next stage",
)
async def advance_stage(task_id: str, req: AdvanceStageRequest) -> StandardSuccessResponse:
    """Advance the pipeline with stage deliverables; blocked if architectural violations are detected."""
    try:
        task_dto = CleanCodePipelineService.advance_stage(task_id, req)
        return create_success_response(data=task_dto.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/tasks/{task_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current state of a Clean-Code assembly pipeline task",
)
async def get_task(task_id: str) -> StandardSuccessResponse:
    """Retrieve full task state including current stage, violations, and artifacts."""
    try:
        task_dto = CleanCodePipelineService.get_task(task_id)
        return create_success_response(data=task_dto.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/tasks",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List all Clean-Code assembly tasks",
)
async def list_tasks(session_id: str | None = Query(default=None)) -> StandardSuccessResponse:
    """List tasks filtered optionally by session_id."""
    tasks = CleanCodePipelineService.list_tasks(session_id=session_id)
    return create_success_response(data=[t.model_dump() for t in tasks])


@router.post(
    "/linter/check",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform AST architecture linting and cyclic dependency analysis on source code map",
)
async def run_linter(req: LinterCheckRequest) -> StandardSuccessResponse:
    """Run static AST dependency analysis and return violations with DIP recommendations."""
    result = CleanCodePipelineService.run_linter(req)
    return create_success_response(data=result.model_dump())
