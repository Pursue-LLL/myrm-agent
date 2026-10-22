"""FastAPI router for Creator Mode Guardrailed Preset Synthesizer and Defensive Sandbox (Item 39).

[INPUT]
- app.schemas.creator_mode::{
    SynthesizePresetRequest,
    VerifyInSandboxRequest,
    RoamingSyncRequest,
  }
- app.services.agent.creator_mode_service::{
    CreatorModeService,
    get_creator_mode_service,
  }

[OUTPUT]
- Router mounted under /agents/creator-mode.

[POS]
- HTTP endpoints for natural language preset synthesis, defensive sandbox certification, and multi-platform roaming.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.creator_mode import (
    RoamingSyncRequest,
    SynthesizePresetRequest,
    VerifyInSandboxRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.creator_mode_service import (
    CreatorModeService,
    get_creator_mode_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/creator-mode", tags=["Creator Mode & Defensive Sandbox"])


@router.post(
    "/synthesize",
    response_model=StandardSuccessResponse,
    summary="Compile natural language intent into guardrailed agent preset draft",
)
def synthesize_preset_endpoint(
    req: SynthesizePresetRequest = ...,
    service: CreatorModeService = Depends(get_creator_mode_service),
) -> StandardSuccessResponse:
    """Analyze natural language description and generate least-privilege tool allowlists and system prompt."""
    try:
        draft = service.synthesize_preset(req=req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return create_success_response(data=draft)


@router.post(
    "/verify-sandbox",
    response_model=StandardSuccessResponse,
    summary="Execute defensive sandbox test battery against preset draft",
)
def verify_in_sandbox_endpoint(
    req: VerifyInSandboxRequest = ...,
    service: CreatorModeService = Depends(get_creator_mode_service),
) -> StandardSuccessResponse:
    """Simulate execution in an isolated sandbox, certifying capability checks and blocking exploits."""
    report = service.verify_in_sandbox(req=req)
    return create_success_response(data=report)


@router.post(
    "/roaming-sync",
    response_model=StandardSuccessResponse,
    summary="Broadcast preset across WebUI, Desktop Tauri, and Cloud with auto-healing",
)
def sync_roaming_preset_endpoint(
    req: RoamingSyncRequest = ...,
    service: CreatorModeService = Depends(get_creator_mode_service),
) -> StandardSuccessResponse:
    """Deploy preset to unified profile storage, automatically repairing broken legacy paths."""
    res = service.sync_roaming(req=req)
    return create_success_response(data=res)


@router.get(
    "/records",
    response_model=StandardSuccessResponse,
    summary="List all synchronized multi-platform preset records",
)
def list_roaming_records_endpoint(
    service: CreatorModeService = Depends(get_creator_mode_service),
) -> StandardSuccessResponse:
    """Retrieve full catalog of multi-platform roaming records and self-healing indicators."""
    records = service.list_roaming_records()
    return create_success_response(data=records)
