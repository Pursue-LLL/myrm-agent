"""router (FastAPI APIRouter for Experience Injection Suite).

[POS]
app/api/memory/experience_injection_router.py

[INPUT]
- app.schemas.experience_injection, app.services.memory.experience_injection_service

[OUTPUT]
- router (FastAPI APIRouter for Experience Injection Suite)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.experience_injection import (
    InjectSkillExperienceRequest,
    InjectSkillExperienceResponseDTO,
    InjectSubagentExperienceRequest,
    InjectSubagentExperienceResponseDTO,
    PreWriteCheckRequest,
    PreWriteCheckResponseDTO,
)
from app.services.memory.experience_injection_service import (
    ExperienceInjectionService,
    get_experience_injection_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experience-injection", tags=["Experience Injection Suite"])


@router.post(
    "/skill-load",
    response_model=InjectSkillExperienceResponseDTO,
    summary="Inject procedure experiences upon skill load",
)
async def inject_skill_load(
    request: InjectSkillExperienceRequest,
    service: Annotated[ExperienceInjectionService, Depends(get_experience_injection_service)],
) -> InjectSkillExperienceResponseDTO:
    """Enrich skill markdown content with relevant procedure experiences and anti-patterns."""
    return service.inject_skill_load(request)


@router.post(
    "/subagent-spawn",
    response_model=InjectSubagentExperienceResponseDTO,
    summary="Inject procedure experiences prior to subagent dispatch",
)
async def inject_subagent_spawn(
    request: InjectSubagentExperienceRequest,
    service: Annotated[ExperienceInjectionService, Depends(get_experience_injection_service)],
) -> InjectSubagentExperienceResponseDTO:
    """Enrich subagent task prompt with procedure memories matching role and delegated task."""
    return service.inject_subagent_spawn(request)


@router.post(
    "/pre-write",
    response_model=PreWriteCheckResponseDTO,
    summary="Evaluate mutating tool calls against immutable boundaries",
)
async def pre_write_check(
    request: PreWriteCheckRequest,
    service: Annotated[ExperienceInjectionService, Depends(get_experience_injection_service)],
) -> PreWriteCheckResponseDTO:
    """Inspect planned mutating tool call and recommend one-time rollback with immutable boundary guards."""
    return service.pre_write_check(request)


@router.post(
    "/reset-turn",
    summary="Reset per-message rollback flag",
)
async def reset_turn(
    service: Annotated[ExperienceInjectionService, Depends(get_experience_injection_service)],
) -> dict[str, str]:
    """Reset message turn state to permit pre-write guard on subsequent user turns."""
    service.reset_message_turn()
    return {"status": "ok", "message": "Turn state reset successfully"}
