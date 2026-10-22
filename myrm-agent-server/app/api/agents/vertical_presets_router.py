"""FastAPI router for Five Vertical Role Persona Presets and Sub-Bot Sandbox Tester (Item 64).

[INPUT]
- app.schemas.vertical_presets::{
    RegisterPresetRequest, SubBotTestRequestDTO, RecordA2AStepRequest, VerticalRoleCategoryDTOEnum,
  }
- app.services.agent.vertical_presets_service::VerticalPresetsService

[OUTPUT]
- REST endpoints under /agents/vertical-presets for preset querying, registration, sandbox test execution, and A2A trace inspection.

[POS]
- HTTP API layer for Item 64 vertical role presets, sandbox test runs, and A2A telemetry.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.vertical_presets import (
    RecordA2AStepRequest,
    RegisterPresetRequest,
    SubBotTestRequestDTO,
    VerticalRoleCategoryDTOEnum,
)
from app.services.agent.vertical_presets_service import VerticalPresetsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/vertical-presets",
    tags=["Five Vertical Role Presets & Sandbox Tester"],
)


@router.get(
    "",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List vertical persona presets",
)
async def list_presets(
    category: VerticalRoleCategoryDTOEnum | None = Query(
        default=None,
        description="Filter presets by persona category",
    ),
) -> StandardSuccessResponse:
    """List out-of-the-box vertical persona presets, optionally filtered by category."""
    try:
        presets = VerticalPresetsService.list_presets(category=category)
        return create_success_response(data=[p.model_dump() for p in presets])
    except Exception as exc:
        logger.exception("Failed to list vertical presets: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/{role_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get preset details by role ID",
)
async def get_preset(role_id: str) -> StandardSuccessResponse:
    """Fetch details for a specific persona preset."""
    try:
        preset = VerticalPresetsService.get_preset(role_id)
        if preset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preset with role ID '{role_id}' not found",
            )
        return create_success_response(data=preset.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get vertical preset: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a vertical role preset",
)
async def register_preset(req: RegisterPresetRequest) -> StandardSuccessResponse:
    """Register or update a specialist persona preset."""
    try:
        preset = VerticalPresetsService.register_preset(req)
        return create_success_response(data=preset.model_dump())
    except Exception as exc:
        logger.exception("Failed to register vertical preset: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/test-sandbox",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Run isolated unit test for a sub-bot",
)
async def run_sandbox_test(req: SubBotTestRequestDTO) -> StandardSuccessResponse:
    """Execute an isolated sandbox test run for a specialist bot and collect telemetry."""
    try:
        result = VerticalPresetsService.run_sandbox_test(req)
        return create_success_response(data=result.model_dump())
    except Exception as exc:
        logger.exception("Failed to execute sandbox test: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/traces/record",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Record an A2A communication step",
)
async def record_a2a_step(req: RecordA2AStepRequest) -> StandardSuccessResponse:
    """Record an interaction step in the A2A communication chain and evaluate loop risk."""
    try:
        trace = VerticalPresetsService.record_a2a_step(
            session_id=req.session_id,
            root_agent_id=req.root_agent_id,
            step_dto=req.step,
        )
        return create_success_response(data=trace.model_dump())
    except Exception as exc:
        logger.exception("Failed to record A2A step: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/traces/{session_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get A2A communication trace for a session",
)
async def get_a2a_trace(session_id: str) -> StandardSuccessResponse:
    """Retrieve full A2A communication trace and loop detection diagnosis for a session."""
    try:
        trace = VerticalPresetsService.get_a2a_trace(session_id)
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No A2A trace found for session '{session_id}'",
            )
        return create_success_response(data=trace.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get A2A trace: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
