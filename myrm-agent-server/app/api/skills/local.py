"""Local skills management endpoints

Endpoints for managing local filesystem skills (local mode only).
"""

import logging

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.skills._deploy_capability import require_local_skills_capability
from app.api.skills.schemas import (
    LocalSkillPathAdoptRequest,
    LocalSkillPathAdoptResponse,
    LocalSkillPathPreviewRequest,
    LocalSkillPathPreviewResponse,
    LocalSkillPathsRequest,
    LocalSkillPathsResponse,
    LocalSkillPreviewItem,
    SkillListResponse,
    ToggleLocalSkillRequest,
    ToggleLocalSkillResponse,
    skill_to_response,
)
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


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
    require_local_skills_capability()
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


@router.post("/local/paths/preview", response_model=LocalSkillPathPreviewResponse)
async def preview_local_skill_path(
    request: LocalSkillPathPreviewRequest,
) -> LocalSkillPathPreviewResponse:
    """Dry-run preview skills in a given local path before adding it."""
    require_local_skills_capability()

    raw_path = request.path.strip()
    if not (raw_path.startswith("/") or raw_path.startswith("~")):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid path format: {raw_path}. Must be absolute path or start with ~",
        )

    # Fetch existing skills across types to detect naming conflicts
    existing_skills = await skills_service.list_skills()

    resolved_path, exists, is_directory, items, warning_msg = (
        skills_service.local_skills.preview_path(
            raw_path=raw_path,
            existing_skills=existing_skills,
        )
    )

    preview_items = [
        LocalSkillPreviewItem(
            name=str(it["name"]),
            description=str(it["description"]),
            version=str(it["version"]),
            author=str(it["author"]) if it.get("author") else None,
            category=str(it["category"]) if it.get("category") else None,
            tags=[str(t) for t in it.get("tags", [])] if isinstance(it.get("tags"), list) else [],
            required_tools=[str(b) for b in it.get("required_tools", [])]
            if isinstance(it.get("required_tools"), list)
            else [],
            relative_path=str(it["relative_path"]),
            skill_id=str(it.get("skill_id", "")),
            is_conflicted=bool(it["is_conflicted"]),
            conflict_reason=str(it["conflict_reason"]) if it.get("conflict_reason") else None,
            is_safe=bool(it["is_safe"]),
            threat_summary=str(it["threat_summary"]) if it.get("threat_summary") else None,
        )
        for it in items
    ]

    return LocalSkillPathPreviewResponse(
        resolved_path=str(resolved_path),
        exists=exists,
        is_directory=is_directory,
        total_discovered=len(preview_items),
        skills=preview_items,
        warning_message=warning_msg,
    )


@router.post("/local/paths/adopt", response_model=LocalSkillPathAdoptResponse)
async def adopt_local_skill_path(
    request: LocalSkillPathAdoptRequest,
) -> LocalSkillPathAdoptResponse:
    """Adopt a local skill path: adds path to config and enables selected skills."""
    require_local_skills_capability()

    raw_path = request.path.strip()
    if not (raw_path.startswith("/") or raw_path.startswith("~")):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid path format: {raw_path}. Must be absolute path or start with ~",
        )

    config = await skills_service.user_config.get_config()
    current_paths = list(config.local_skill_paths)
    if raw_path not in current_paths:
        current_paths.append(raw_path)
        config = await skills_service.user_config.update_local_skill_paths(current_paths)
        added_to_paths = True
    else:
        added_to_paths = False

    adopted_skill_ids: list[str] = []
    for sid in request.selected_skill_ids:
        sid_clean = sid.strip()
        if sid_clean and sid_clean.startswith("local::"):
            await skills_service.user_config.enable_local_skill(sid_clean)
            adopted_skill_ids.append(sid_clean)

    agent_adopted = False
    if request.agent_id:
        try:
            from app.core.skills.discovery.adopt import complete_discovery_adoption

            for sid in adopted_skill_ids:
                res = await complete_discovery_adoption(request.agent_id, sid)
                if res.allowlist_appended:
                    agent_adopted = True
        except Exception as e:
            logger.warning("Agent adoption failed for agent %s: %s", request.agent_id, e)

    return LocalSkillPathAdoptResponse(
        status="ok",
        path=raw_path,
        added_to_paths=added_to_paths,
        adopted_skills_count=len(adopted_skill_ids),
        adopted_skill_ids=adopted_skill_ids,
        agent_adopted=agent_adopted,
        agent_id=request.agent_id,
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
    require_local_skills_capability()

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
    require_local_skills_capability()

    # Only get LOCAL type skills
    skills = await skills_service.list_skills(
        skill_type=SkillType.LOCAL,
    )

    return SkillListResponse(
        skills=[skill_to_response(s) for s in skills],
        total=len(skills),
    )
