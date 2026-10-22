"""FastAPI router for Skill Bundles Batch Manifest & Lifecycle Warmup Manager (Item 41).

[INPUT]
- app.schemas.skill_bundle::{
    RegisterBundleRequest,
    WarmupBundleRequest,
    ActivateBundleRequest,
    DeactivateBundleRequest,
    BundleCategoryEnum,
  }
- app.services.agent.skill_bundle_service::{
    SkillBundleService,
    get_skill_bundle_service,
  }

[OUTPUT]
- Routers mounted under /skills/bundles and /chats/{chat_id}/skill-bundles.

[POS]
- HTTP endpoints for scenario bundle discovery, pre-flight warmup diagnostic probes,
  and atomic one-click session mounting.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from myrm_agent_harness.agent.skills.bundle_warmup import (
    SkillBundleError,
    SkillBundleWarmupBlockedError,
)

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.skill_bundle import (
    ActivateBundleRequest,
    BundleCategoryEnum,
    DeactivateBundleRequest,
    RegisterBundleRequest,
    WarmupBundleRequest,
)
from app.services.agent.skill_bundle_service import (
    SkillBundleService,
    get_skill_bundle_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Skill Bundles"])


@router.get(
    "/skills/bundles",
    response_model=StandardSuccessResponse,
    summary="List registered scenario-based skill bundles",
)
def list_bundles_endpoint(
    category: BundleCategoryEnum | None = Query(default=None, description="Optional category filter"),
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Retrieve catalog of skill bundles, optionally filtered by business vertical."""
    bundles = service.list_bundles(category)
    return create_success_response([b.model_dump() for b in bundles])


@router.post(
    "/skills/bundles",
    response_model=StandardSuccessResponse,
    summary="Register or update a skill bundle manifest",
)
def register_bundle_endpoint(
    req: RegisterBundleRequest,
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Register a new scenario bundle manifest with dependency declarations."""
    try:
        registered = service.register_bundle(req.manifest)
        return create_success_response(registered.model_dump())
    except SkillBundleError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/skills/bundles/{bundle_id}",
    response_model=StandardSuccessResponse,
    summary="Get skill bundle details by bundle ID",
)
def get_bundle_endpoint(
    bundle_id: str = Path(..., min_length=1, description="Bundle ID"),
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Retrieve detailed manifest specification for a specific bundle."""
    bundle = service.get_bundle(bundle_id)
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill bundle '{bundle_id}' not found.",
        )
    return create_success_response(bundle.model_dump())


@router.post(
    "/skills/bundles/{bundle_id}/warmup",
    response_model=StandardSuccessResponse,
    summary="Run diagnostic pre-flight warmup checks on bundle",
)
def warmup_bundle_endpoint(
    bundle_id: str = Path(..., min_length=1, description="Bundle ID"),
    req: WarmupBundleRequest = ...,
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Run pre-flight checks against skills availability, env vars, and required tools."""
    try:
        report = service.warmup_bundle(
            bundle_id=bundle_id,
            available_skills=req.available_skills,
            env_vars=req.env_vars,
            available_tools=req.available_tools if req.available_tools else None,
        )
        return create_success_response(report.model_dump())
    except SkillBundleError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/chats/{chat_id}/skill-bundles/activate",
    response_model=StandardSuccessResponse,
    summary="Atomically activate all skills in a bundle for a chat session",
)
def activate_bundle_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: ActivateBundleRequest = ...,
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Atomically activate bundle skills in current chat with warmup pre-flight gating."""
    try:
        record = service.activate_bundle(
            session_id=chat_id,
            bundle_id=req.bundle_id,
            available_skills=req.available_skills,
            env_vars=req.env_vars,
            force=req.force,
        )
        return create_success_response(record.model_dump())
    except SkillBundleWarmupBlockedError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    except SkillBundleError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/chats/{chat_id}/skill-bundles/deactivate",
    response_model=StandardSuccessResponse,
    summary="Deactivate a bundle from a chat session",
)
def deactivate_bundle_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: DeactivateBundleRequest = ...,
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Remove a previously activated bundle from the chat session."""
    deactivated = service.deactivate_bundle(session_id=chat_id, bundle_id=req.bundle_id)
    return create_success_response({"deactivated": deactivated, "bundle_id": req.bundle_id})


@router.get(
    "/chats/{chat_id}/skill-bundles/active",
    response_model=StandardSuccessResponse,
    summary="List active skill bundles in chat session",
)
def list_active_bundles_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: SkillBundleService = Depends(get_skill_bundle_service),
) -> StandardSuccessResponse:
    """Retrieve all active skill bundle records mounted in the chat session."""
    records = service.get_session_activations(chat_id)
    return create_success_response([r.model_dump() for r in records])
