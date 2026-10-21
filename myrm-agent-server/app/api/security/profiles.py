"""Security Profiles API — CRUD endpoints for named security configuration profiles.

Provides list, get, create, update, delete, clone, and activate operations.
Builtin profiles (readonly, workspace, full_access) are auto-seeded and protected.

[INPUT]
- app.services.security.profile_manager::ProfileManager
- app.api.security.schemas::ProfileResponse, ProfileCreateRequest, etc.

[OUTPUT]
- router: FastAPI APIRouter for /security/profiles endpoints

[POS]
REST API layer for security profile management.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.security.schemas import (
    ProfileCloneRequest,
    ProfileCreateRequest,
    ProfileListResponse,
    ProfileResponse,
)
from app.services.security.profile_manager import ProfileManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security/profiles", tags=["security-profiles"])

_manager = ProfileManager()


@router.get("", response_model=ProfileListResponse)
async def list_profiles() -> ProfileListResponse:
    """List all security profiles (builtins auto-seeded)."""
    profiles = await _manager.list_all()
    active = await _manager.get_active()
    return ProfileListResponse(
        profiles=[ProfileResponse(**p) for p in profiles],
        activeKey=active.get("profile_key") if active else None,
    )


@router.get("/{profile_key}", response_model=ProfileResponse)
async def get_profile(profile_key: str) -> ProfileResponse:
    """Get a single profile by key."""
    profile = await _manager.get(profile_key)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_key}' not found")
    return ProfileResponse(**profile)


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(req: ProfileCreateRequest) -> ProfileResponse:
    """Create or update a custom profile."""
    try:
        profile = await _manager.save(
            profile_key=req.profile_key,
            display_name=req.display_name,
            config_json=req.config_json,
            description=req.description,
        )
        return ProfileResponse(**profile)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.put("/{profile_key}", response_model=ProfileResponse)
async def update_profile(profile_key: str, req: ProfileCreateRequest) -> ProfileResponse:
    """Update an existing profile."""
    try:
        profile = await _manager.save(
            profile_key=profile_key,
            display_name=req.display_name,
            config_json=req.config_json,
            description=req.description,
        )
        return ProfileResponse(**profile)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.delete("/{profile_key}", status_code=204)
async def delete_profile(profile_key: str) -> None:
    """Delete a custom profile. Builtin profiles cannot be deleted."""
    try:
        deleted = await _manager.delete(profile_key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_key}' not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/clone", response_model=ProfileResponse, status_code=201)
async def clone_profile(req: ProfileCloneRequest) -> ProfileResponse:
    """Clone an existing profile under a new key."""
    try:
        profile = await _manager.clone(
            source_key=req.source_key,
            new_key=req.new_key,
            new_display_name=req.new_display_name,
        )
        return ProfileResponse(**profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{profile_key}/activate", response_model=ProfileResponse)
async def activate_profile(profile_key: str) -> ProfileResponse:
    """Set a profile as the active one."""
    profile = await _manager.activate(profile_key)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_key}' not found")
    return ProfileResponse(**profile)
