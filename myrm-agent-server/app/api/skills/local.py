"""Local skills management endpoints

[INPUT]
- LocalSkillPathsRequest, LocalSkillPathPreviewRequest, LocalSkillPathAdoptRequest

[OUTPUT]
- LocalSkillPathsResponse, LocalSkillPathPreviewResponse, LocalSkillPathAdoptResponse

[POS]
- api/skills/local.py: HTTP endpoints for local skill paths inspection and adoption
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
    LocalSkillPathStatus,
    LocalSkillPreviewItem,
    SecurityFindingResponse,
    SecurityScanSummaryResponse,
    SkillListResponse,
    ToggleLocalSkillRequest,
    ToggleLocalSkillResponse,
    skill_to_response,
)
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _probe_path_status(raw_path: str) -> LocalSkillPathStatus:
    """Helper to inspect the health and skill count of a configured path without side effects."""
    resolved_path, exists, is_directory, items, warning_msg = skills_service.local_skills.preview_path(raw_path=raw_path)
    skill_names = [str(it.get("name", "")) for it in items if it.get("name")]
    return LocalSkillPathStatus(
        path=raw_path,
        resolved_path=str(resolved_path),
        exists=exists,
        is_directory=is_directory,
        skills_count=len(skill_names),
        skill_names=skill_names,
        warning_message=warning_msg,
    )


@router.get("/local/paths", response_model=LocalSkillPathsResponse)
async def get_local_skill_paths() -> LocalSkillPathsResponse:
    """Get user's configured local skill paths

    Returns:
        Local skill paths configuration
    """
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    config = await skills_service.user_config.get_config()
    statuses = [_probe_path_status(p) for p in config.local_skill_paths]

    return LocalSkillPathsResponse(
        paths=config.local_skill_paths,
        default_paths=DEFAULT_LOCAL_SKILL_PATHS,
        path_statuses=statuses,
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

    # Validate path format (must be absolute path or start with ~, no traversal)
    for path in request.paths:
        if not (path.startswith("/") or path.startswith("~")):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path format: {path}. Must be absolute path or start with ~",
            )
        if ".." in path:
            raise HTTPException(
                status_code=400,
                detail=f"Path traversal not allowed: {path}",
            )

    # Update configuration
    config = await skills_service.user_config.update_local_skill_paths(
        paths=request.paths,
    )
    statuses = [_probe_path_status(p) for p in config.local_skill_paths]

    return LocalSkillPathsResponse(
        paths=config.local_skill_paths,
        default_paths=DEFAULT_LOCAL_SKILL_PATHS,
        path_statuses=statuses,
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
    if ".." in raw_path:
        raise HTTPException(
            status_code=400,
            detail="Path traversal not allowed",
        )

    # Fetch existing skills across types to detect naming conflicts
    existing_skills = await skills_service.list_skills()

    resolved_path, exists, is_directory, items, warning_msg = skills_service.local_skills.preview_path(
        raw_path=raw_path,
        existing_skills=existing_skills,
    )

    preview_items: list[LocalSkillPreviewItem] = []
    for it in items:
        sec_dict = it.get("security")
        sec_resp: SecurityScanSummaryResponse | None = None
        if isinstance(sec_dict, dict):
            findings_raw = sec_dict.get("findings", [])
            findings_list = [
                SecurityFindingResponse(
                    threat_type=str(f.get("threat_type", "")),
                    severity=str(f.get("severity", "")),
                    description=str(f.get("description", "")),
                    line_number=(int(f["line_number"]) if f.get("line_number") is not None else None),
                )
                for f in findings_raw
                if isinstance(f, dict)
            ] if isinstance(findings_raw, list) else []
            fc_raw = sec_dict.get("finding_counts", {})
            finding_counts = {str(k): int(v) for k, v in fc_raw.items()} if isinstance(fc_raw, dict) else {}
            sec_resp = SecurityScanSummaryResponse(
                score=int(sec_dict.get("score", 100)),
                trust_recommendation=str(sec_dict.get("trust_recommendation", "trusted")),
                finding_counts=finding_counts,
                total_findings=int(sec_dict.get("total_findings", 0)),
                findings=findings_list,
            )

        preview_items.append(
            LocalSkillPreviewItem(
                name=str(it["name"]),
                description=str(it["description"]),
                version=str(it["version"]),
                author=str(it["author"]) if it.get("author") else None,
                category=str(it["category"]) if it.get("category") else None,
                tags=([str(t) for t in it.get("tags", [])] if isinstance(it.get("tags"), list) else []),
                required_tools=([str(b) for b in it.get("required_tools", [])] if isinstance(it.get("required_tools"), list) else []),
                relative_path=str(it["relative_path"]),
                skill_id=str(it.get("skill_id", "")),
                is_conflicted=bool(it["is_conflicted"]),
                conflict_reason=(str(it["conflict_reason"]) if it.get("conflict_reason") else None),
                is_safe=bool(it["is_safe"]),
                threat_summary=(str(it["threat_summary"]) if it.get("threat_summary") else None),
                security_score=int(it.get("security_score", 100)),
                security=sec_resp,
            )
        )

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
    if ".." in raw_path:
        raise HTTPException(
            status_code=400,
            detail="Path traversal not allowed",
        )

    # Preflight security gate: probe path and block adopting skills with score < 50 unless allow_untrusted=True
    if request.selected_skill_ids:
        _, _, _, preview_items_raw, _ = skills_service.local_skills.preview_path(raw_path=raw_path)
        preview_by_id = {str(item.get("skill_id")): item for item in preview_items_raw if item.get("skill_id")}
        for sid in request.selected_skill_ids:
            item = preview_by_id.get(sid.strip())
            if not item:
                continue
            raw_score = item.get("security_score")
            score = int(raw_score) if raw_score is not None else (100 if item.get("is_safe", True) else 40)
            if score < 50:
                if not request.allow_untrusted:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Security gate blocked: Skill '{item.get('name')}' has a security score of {score}/100 (< 50 threshold). {item.get('threat_summary', '')}. Explicit administrator override required to adopt untrusted skills.",
                    )
                logger.warning(
                    "AUDIT_EVENT: SKILL_SECURITY_OVERRIDE path=%s skill_id=%s score=%d operator_action=allow_untrusted",
                    raw_path,
                    sid.strip(),
                    score,
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
