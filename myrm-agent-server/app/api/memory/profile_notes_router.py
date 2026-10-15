"""API router for Dual-Layer Profile & Working Notes Memory Budget Guard.

[INPUT]
- fastapi::APIRouter, Depends
- app.schemas.profile_notes::ProfileNotesIntakeRequest, ProfileNotesIntakeResponse
- app.schemas.profile_notes::ProfileNotesUpdateRequest, ProfileNotesContentResponse
- app.services.memory.profile_notes_service::ProfileNotesService, get_profile_notes_service

[OUTPUT]
- router: APIRouter exporting endpoints for intake filtering and content management

[POS]
REST API surface for User Profile and Working Notes governance, enabling UI HUD display
and proactive intake validation against ephemeral noise.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.profile_notes import (
    ProfileNotesContentResponse,
    ProfileNotesIntakeRequest,
    ProfileNotesIntakeResponse,
    ProfileNotesUpdateRequest,
)
from app.services.memory.profile_notes_service import (
    ProfileNotesService,
    get_profile_notes_service,
)

router = APIRouter(prefix="/profile-notes", tags=["memory-profile-notes"])


@router.post("/intake-check", response_model=ProfileNotesIntakeResponse)
async def check_intake_noise(
    request: ProfileNotesIntakeRequest,
    service: Annotated[ProfileNotesService, Depends(get_profile_notes_service)],
) -> ProfileNotesIntakeResponse:
    """Evaluate candidate text against ephemeral noise filters."""
    return service.evaluate_intake(
        content=request.content,
        layer_hint_str=request.layer_hint,
    )


@router.get("/contents", response_model=ProfileNotesContentResponse)
async def get_layer_contents(
    service: Annotated[ProfileNotesService, Depends(get_profile_notes_service)],
) -> ProfileNotesContentResponse:
    """Retrieve full content and watermark status for USER and MEMORY layers."""
    return service.get_contents()


@router.put("/contents", response_model=ProfileNotesContentResponse)
async def update_layer_contents(
    request: ProfileNotesUpdateRequest,
    service: Annotated[ProfileNotesService, Depends(get_profile_notes_service)],
) -> ProfileNotesContentResponse:
    """Update USER and/or MEMORY content while checking capacity budgets."""
    return service.update_contents(
        user_content=request.user_content,
        memory_content=request.memory_content,
    )
