"""Local skills management endpoints

Endpoints for managing local filesystem skills (local mode only).
"""

import logging

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.skills.schemas import (
    LocalSkillPathsRequest,
    LocalSkillPathsResponse,
    SkillListResponse,
    ToggleLocalSkillRequest,
    ToggleLocalSkillResponse,
    skill_to_response,
)
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_local_skills_capability() -> None:
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().allows_local_skills:
        raise HTTPException(
            status_code=403,
            detail="Local skills are not available in sandbox mode",
        )


@router.get("/local/paths", response_model=LocalSkillPathsResponse)
async def get_local_skill_paths() -> LocalSkillPathsResponse:
    """Get user's configured local skill paths

    Returns:
        Local skill paths configuration
    """
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    config = await skills_service.user_config.get_config()

    return LocalSkillPathsResponse(
        paths=config.local_skill_paths,
        default_paths=DEFAULT_LOCAL_SKILL_PATHS,
    )


@router.put("/local/paths", response_model=LocalSkillPathsResponse)
async def update_local_skill_paths(
    request: LocalSkillPathsRequest,
) -> LocalSkillPathsResponse:
    """Update user's local skill paths configuration

    Args:
        request: Paths list

    Returns:
        Updated paths configuration
    """
    _require_local_skills_capability()
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    # Validate path format (must be absolute path or start with ~)
    for path in request.paths:
        if not (path.startswith("/") or path.startswith("~")):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path format: {path}. Must be absolute path or start with ~",
            )

    # Update configuration
    config = await skills_service.user_config.update_local_skill_paths(
        paths=request.paths,
    )

    return LocalSkillPathsResponse(
        paths=config.local_skill_paths,
        default_paths=DEFAULT_LOCAL_SKILL_PATHS,
    )


@router.post("/local/toggle", response_model=ToggleLocalSkillResponse)
async def toggle_local_skill(
    request: ToggleLocalSkillRequest,
) -> ToggleLocalSkillResponse:
    """Toggle local skill enable/disable status

    Args:
        request: Contains skill ID

    Returns:
        Toggled status
    """
    _require_local_skills_capability()

    # Validate skill ID format
    if not request.skill_id.startswith("local::"):
        raise HTTPException(
            status_code=400,
            detail="Invalid local skill ID format. Must start with 'local::'",
        )

    config = await skills_service.user_config.get_config()
    if request.skill_id in config.enabled_local_skill_ids:
        await skills_service.user_config.disable_local_skill(request.skill_id)
        enabled = False
    else:
        await skills_service.user_config.enable_local_skill(request.skill_id)
        enabled = True
    return ToggleLocalSkillResponse(
        skill_id=request.skill_id,
        enabled=enabled,
    )


@router.post("/local/scan", response_model=SkillListResponse)
async def scan_local_skills() -> SkillListResponse:
    """Scan local skills (refresh)

    Scans all configured local paths for the user and returns found skills.

    Returns:
        List of scanned local skills
    """
    _require_local_skills_capability()

    # Only get LOCAL type skills
    skills = await skills_service.list_skills(
        skill_type=SkillType.LOCAL,
    )

    return SkillListResponse(
        skills=[skill_to_response(s) for s in skills],
        total=len(skills),
    )
