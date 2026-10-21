"""Enable installed skills in user catalog after discovery install.

[INPUT]
- myrm_agent_harness.api.skills::SkillInstallResult (POS: Market install result)
- app.core.skills.providers.local::compute_local_skill_id (POS: Stable local skill ID from path)
- app.core.skills.store.service::skills_service (POS: Skill CRUD and user config)

[OUTPUT]
- resolve_mount_skill_id: Map install result to catalog skill ID
- maybe_mount_after_install: Post-install catalog enable (allowlist append is discovery_adopt)

[POS]
Discovery install catalog enable bridge. Adds installed skills to the user-enabled catalog.
Explicit agent allowlist append is handled by discovery_adopt after mount succeeds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.api.skills import SkillInstallResult

logger = logging.getLogger(__name__)

DEFAULT_MOUNT_AGENT_ID = "builtin-general"


@dataclass(frozen=True)
class SkillMountResult:
    """Install follow-up result. ``mounted`` means enabled in user catalog (API compat name)."""

    mounted: bool
    agent_id: str = ""
    mount_skill_id: str = ""
    already_mounted: bool = False
    error: str = ""


def resolve_mount_skill_id(result: SkillInstallResult) -> str | None:
    """Resolve the skill ID used by the user catalog from an install result."""
    if not result.success:
        return None

    installed_path = result.installed_path.strip()
    if installed_path and installed_path != "prebuilt (already installed)":
        from app.core.skills.providers.local import compute_local_skill_id

        return compute_local_skill_id(Path(installed_path))

    skill_id = result.skill_id.strip()
    if skill_id and not skill_id.startswith("local::"):
        return skill_id

    return skill_id or None


async def _is_skill_enabled(skill_id: str) -> bool:
    from app.core.skills.store.service import skills_service

    config = await skills_service.user_config.get_config()
    if skill_id.startswith("local::"):
        return skill_id in config.enabled_local_skill_ids
    return skill_id in config.enabled_prebuilt_ids


async def _ensure_skill_enabled(skill_id: str) -> None:
    from app.core.skills.config_version import bump_skill_config_version
    from app.core.skills.store.service import skills_service

    if skill_id.startswith("local::"):
        config = await skills_service.user_config.get_config()
        if skill_id not in config.enabled_local_skill_ids:
            await skills_service.user_config.enable_local_skill(skill_id)
    else:
        await skills_service.user_config.enable_prebuilt_skill(skill_id)
    bump_skill_config_version()


async def maybe_mount_after_install(
    result: SkillInstallResult,
    *,
    agent_id: str | None,
    mount_to_agent: bool,
) -> SkillMountResult | None:
    """Enable an installed skill in the user catalog when mount_to_agent is requested."""
    if not mount_to_agent or not result.success:
        return None

    context_agent_id = (agent_id or DEFAULT_MOUNT_AGENT_ID).strip()
    catalog_skill_id = resolve_mount_skill_id(result)
    if not catalog_skill_id:
        return SkillMountResult(
            mounted=False,
            agent_id=context_agent_id,
            error="Could not resolve skill ID for enable",
        )

    already_enabled = await _is_skill_enabled(catalog_skill_id)
    try:
        await _ensure_skill_enabled(catalog_skill_id)
    except Exception as exc:
        logger.warning("Failed to enable skill %s after install: %s", catalog_skill_id, exc)
        return SkillMountResult(
            mounted=False,
            agent_id=context_agent_id,
            mount_skill_id=catalog_skill_id,
            error=f"Failed to enable skill after install: {exc}",
        )

    logger.info(
        "Enabled skill %s in user catalog after discovery install (context agent %s)",
        catalog_skill_id,
        context_agent_id,
    )
    try:
        from app.services.event.app_event_bus import (
            AppEvent,
            AppEventType,
            get_event_bus,
        )

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SKILL_POOL_UPDATED,
                data={
                    "action": "install",
                    "skill_id": catalog_skill_id,
                    "agent_id": context_agent_id,
                },
            )
        )
    except Exception as exc:
        logger.warning("Failed to broadcast SKILL_POOL_UPDATED on mount: %s", exc)

    return SkillMountResult(
        mounted=True,
        agent_id=context_agent_id,
        mount_skill_id=catalog_skill_id,
        already_mounted=already_enabled,
    )
