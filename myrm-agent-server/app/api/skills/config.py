from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.skills.audit import _audit_skill_action
from app.api.skills.schemas import (
    EnableSkillResponse,
    ScanFindingResponse,
    SkillConfigVersionResponse,
    SkillEnvVarsResponse,
    SkillListResponse,
    UpdateSkillEnvVarsRequest,
    UpdateUserSkillConfigRequest,
    UserSkillConfigResponse,
    skill_to_response,
)
from app.core.skills.config_version import bump_skill_config_version, get_skill_config_version
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/config", response_model=UserSkillConfigResponse)
async def get_user_skill_config() -> UserSkillConfigResponse:
    """Get user skill configuration (enabled prebuilt skills and local skill paths)."""
    config = await skills_service.user_config.get_config()
    return UserSkillConfigResponse(
        enabled_prebuilt_ids=config.enabled_prebuilt_ids,
        disabled_prebuilt_ids=config.disabled_prebuilt_ids,
        local_skill_paths=config.local_skill_paths,
        enabled_local_skill_ids=config.enabled_local_skill_ids,
        evolution_strategy=config.evolution_strategy,
        updated_at=config.updated_at.isoformat(),
    )


@router.put("/config", response_model=UserSkillConfigResponse)
async def update_user_skill_config(
    request: UpdateUserSkillConfigRequest,
) -> UserSkillConfigResponse:
    """Update user skill configuration."""
    kwargs: dict[str, object] = {}
    if request.enabled_prebuilt_ids is not None:
        kwargs["enabled_prebuilt_ids"] = request.enabled_prebuilt_ids
    if request.evolution_strategy is not None:
        kwargs["evolution_strategy"] = request.evolution_strategy

    config = await skills_service.user_config.update_config(**kwargs)

    # Hot-update harness screener strategy when changed
    if request.evolution_strategy is not None:
        try:
            from myrm_agent_harness.agent.skills.evolution.infra.integration import (
                get_global_evolution_integration,
            )

            integration = get_global_evolution_integration()
            if integration:
                integration.evolution_strategy = request.evolution_strategy
                logger.info("Evolution strategy hot-updated to '%s'", request.evolution_strategy)
        except Exception as e:
            logger.warning("Failed to hot-update evolution strategy: %s", e)

    bump_skill_config_version()
    return UserSkillConfigResponse(
        enabled_prebuilt_ids=config.enabled_prebuilt_ids,
        disabled_prebuilt_ids=config.disabled_prebuilt_ids,
        local_skill_paths=config.local_skill_paths,
        enabled_local_skill_ids=config.enabled_local_skill_ids,
        evolution_strategy=config.evolution_strategy,
        updated_at=config.updated_at.isoformat(),
    )


@router.post("/{skill_id}/enable", response_model=EnableSkillResponse)
async def enable_skill(skill_id: str, force: bool = False) -> EnableSkillResponse:
    """Enable a skill with pre-enablement security scan.

    For local skills, reads and scans SKILL.md content. If CRITICAL findings
    are detected and force=False, enablement is blocked.
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    from myrm_agent_harness.backends.skills.scanning import ScanSeverity, get_scan_cache, scan_skill_content

    scan_responses: list[ScanFindingResponse] = []

    skill_content = await skills_service.get_skill_file(skill_id, "SKILL.md")
    if skill_content:
        content_str = skill_content.decode("utf-8") if isinstance(skill_content, bytes) else skill_content

        scan_cache = get_scan_cache()
        scan_result = scan_cache.get(content_str)
        if scan_result is None:
            scan_result = scan_skill_content(skill.name, content_str)
            scan_cache.set(content_str, scan_result)
        else:
            logger.debug("Using cached scan result for skill_id=%s", skill_id)

        if not scan_result.is_clean:
            scan_responses = [
                ScanFindingResponse(
                    threat_type=f.threat_type,
                    severity=int(f.severity),
                    description=f.description,
                    line_number=f.line_number,
                )
                for f in scan_result.findings
            ]
            if scan_result.max_severity and scan_result.max_severity >= ScanSeverity.CRITICAL and not force:
                _audit_skill_action("enable_blocked", skill_id, scan_findings=len(scan_responses))
                return EnableSkillResponse(
                    skill_id=skill_id,
                    enabled=False,
                    blocked=True,
                    scan_findings=scan_responses,
                )

    # Check permission requirements (optional on skill model; use getattr for typing)
    required_permissions = getattr(skill, "required_permissions", None)
    if required_permissions:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import SkillPermissionGrant

        async with get_session() as db:
            # Query granted permissions
            stmt = select(SkillPermissionGrant).where(
                SkillPermissionGrant.skill_id == skill_id,
            )
            result = await db.execute(stmt)
            granted = {g.permission for g in result.scalars().all()}

        # Check if all required permissions are granted
        required = {p.value for p in required_permissions}
        missing = required - granted

        if missing:
            # Return pending_approval response
            _audit_skill_action("enable_pending_approval", skill_id)
            return EnableSkillResponse(
                skill_id=skill_id,
                enabled=False,
                pending_approval=True,
                required_permissions=list(missing),
                scan_findings=scan_responses,
            )

    config = await skills_service.user_config.get_config()
    if skill_id.startswith("local::"):
        if skill_id not in config.enabled_local_skill_ids:
            config.enabled_local_skill_ids.append(skill_id)
            await skills_service.user_config.update_config(enabled_local_skill_ids=config.enabled_local_skill_ids)
    else:
        await skills_service.user_config.enable_prebuilt_skill(skill_id)

    bump_skill_config_version()
    _audit_skill_action("enable", skill_id, scan_findings=len(scan_responses))
    return EnableSkillResponse(
        skill_id=skill_id,
        enabled=True,
        blocked=False,
        scan_findings=scan_responses,
    )


@router.post("/{skill_id}/disable", response_model=EnableSkillResponse)
async def disable_skill(skill_id: str) -> EnableSkillResponse:
    """Disable a skill (no scan required)."""
    config = await skills_service.user_config.get_config()

    if skill_id.startswith("local::"):
        if skill_id in config.enabled_local_skill_ids:
            config.enabled_local_skill_ids.remove(skill_id)
            await skills_service.user_config.update_config(enabled_local_skill_ids=config.enabled_local_skill_ids)
    else:
        await skills_service.user_config.disable_prebuilt_skill(skill_id)

    bump_skill_config_version()
    _audit_skill_action("disable", skill_id)
    return EnableSkillResponse(skill_id=skill_id, enabled=False)


@router.post("/{skill_id}/trust")
async def trust_skill(skill_id: str) -> dict[str, str]:
    """Elevate a skill to TRUSTED after user security review."""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    await skills_service.user_config.trust_skill(skill_id)
    bump_skill_config_version()
    _audit_skill_action("trust", skill_id)
    return {"skill_id": skill_id, "trust": "trusted"}


@router.delete("/{skill_id}/trust")
async def untrust_skill(skill_id: str) -> dict[str, str]:
    """Revoke user trust from a skill, reverting to its original trust level."""
    await skills_service.user_config.untrust_skill(skill_id)
    bump_skill_config_version()
    _audit_skill_action("untrust", skill_id)
    return {"skill_id": skill_id, "trust": "revoked"}


@router.post("/{skill_id}/evolution-lock")
async def toggle_evolution_lock(skill_id: str, locked: bool = True) -> dict[str, str | bool]:
    """Lock or unlock a skill's auto-evolution.

    Locked skills are protected from being modified by the Agent's
    auto-evolution system, preserving user-edited content.

    Args:
        skill_id: Skill ID
        locked: True to lock (default), False to unlock
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    try:
        from myrm_agent_harness.agent.skills.evolution.infra.integration import (
            get_global_evolution_integration,
        )

        evolution = get_global_evolution_integration()
        if not evolution or not evolution.store:
            raise HTTPException(status_code=503, detail="Evolution system not initialized")

        await evolution.store.set_evolution_lock(skill_id, locked=locked)

        # Double-write to local SKILL.md file if it exists
        if skill.storage_path:
            from pathlib import Path

            from myrm_agent_harness.backends.skills._utils import update_frontmatter_evolution_lock

            skill_md_path = Path(skill.storage_path) / "SKILL.md"
            if skill_md_path.exists():
                update_frontmatter_evolution_lock(skill_md_path, locked)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update evolution lock: {e}") from e

    action = "evolution_lock" if locked else "evolution_unlock"
    _audit_skill_action(action, skill_id)
    return {"skill_id": skill_id, "evolution_locked": locked}


@router.get("/{skill_id}/env", response_model=SkillEnvVarsResponse)
async def get_skill_env_vars(skill_id: str) -> SkillEnvVarsResponse:
    """Get configured env vars for a skill."""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    config = await skills_service.user_config.get_config()
    env_vars = config.skill_env_vars.get(skill_id, {})

    return SkillEnvVarsResponse(
        skill_id=skill_id,
        env_vars=env_vars,
        required_env=skill.requires.env,
        primary_env=skill.primary_env,
    )


@router.put("/{skill_id}/env", response_model=SkillEnvVarsResponse)
async def update_skill_env_vars(
    skill_id: str,
    request: UpdateSkillEnvVarsRequest,
) -> SkillEnvVarsResponse:
    """Save env var configuration for a skill."""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    config = await skills_service.user_config.get_config()
    config.skill_env_vars[skill_id] = request.env_vars
    await skills_service.user_config.save_config(config)

    bump_skill_config_version()
    return SkillEnvVarsResponse(
        skill_id=skill_id,
        env_vars=request.env_vars,
        required_env=skill.requires.env,
        primary_env=skill.primary_env,
    )


@router.get("/config-version", response_model=SkillConfigVersionResponse)
async def get_config_version() -> SkillConfigVersionResponse:
    """Return skill config version for hot-reload detection.

    Agents poll this endpoint to detect skill configuration changes
    (enable/disable/env updates) and reload their active skill set.
    """
    return SkillConfigVersionResponse(version=get_skill_config_version())


@router.get("/available", response_model=SkillListResponse)
async def get_user_available_skills() -> SkillListResponse:
    """Get user's available skills (enabled prebuilt + local skills)."""
    skills = await skills_service.get_user_available_skills()
    return SkillListResponse(
        skills=[skill_to_response(s) for s in skills],
        total=len(skills),
    )
