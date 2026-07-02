"""Marketplace import — install Agent profile from marketplace package.

Takes a marketplace package (exported via marketplace_export) and creates
the Agent plus all missing dependencies in the local sandbox. Skills are
created via SkillCreationService; Agents are persisted via AgentService.

[INPUT]
- core.skills.creation.service::SkillCreationService (POS: Skill 写入服务)
- services.agent.agent_service::AgentService (POS: Agent CRUD 服务)
- Marketplace package dict (from marketplace_export)

[OUTPUT]
- import_agent_package(skill_svc, package): Creates Agent + dependencies, returns new Agent ID

[POS]
Server-side import for marketplace install flow. Resolves Skill dependencies
via SkillCreationService, remaps Skill/Subagent IDs, and creates a ready-to-use Agent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.skills.creation.service import SkillCreationService

logger = logging.getLogger(__name__)


async def import_agent_package(
    skill_svc: "SkillCreationService",
    package: dict,
) -> str:
    """Import a marketplace package into the local sandbox.

    Args:
        skill_svc: SkillCreationService for writing Skills to filesystem.
        package: Marketplace package dict from export.

    Returns:
        New Agent ID.
    """
    agent_profile = package.get("agent_profile", {})
    bundled_skills = package.get("bundled_skills", [])
    bundled_subagents = package.get("bundled_subagents", [])

    skill_id_map = await _install_skills(skill_svc, bundled_skills)

    subagent_id_map = await _create_subagents(bundled_subagents, skill_id_map)
    remapped_profile = _remap_ids(agent_profile, skill_id_map, subagent_id_map)
    new_agent_id = await _create_agent(remapped_profile)

    logger.info(
        "Imported marketplace agent '%s' as %s (skills: %d, subagents: %d)",
        remapped_profile.get("display_name", "unnamed"),
        new_agent_id,
        len(bundled_skills),
        len(subagent_id_map),
    )
    return new_agent_id


async def _install_skills(
    skill_svc: "SkillCreationService",
    bundled_skills: list[dict],
) -> dict[str, str]:
    """Install bundled Skills via SkillCreationService.

    Returns:
        Mapping of old skill ID -> new local skill ID.
    """
    id_map: dict[str, str] = {}

    for skill_def in bundled_skills:
        name = skill_def.get("name", "")
        content = skill_def.get("content", "")
        description = skill_def.get("description", "")
        original_id = skill_def.get("id", "")

        if not name or not content:
            logger.warning("Skipping malformed skill bundle (missing name or content)")
            continue

        try:
            result = await skill_svc.save_skill(name, content, description)
            if result.success and result.skill_id:
                id_map[original_id] = result.skill_id
            else:
                logger.warning(
                    "Failed to save skill '%s': %s", name, result.error
                )
                continue
        except Exception:
            logger.warning("Failed to install skill '%s'", name, exc_info=True)
            continue

        resources: dict[str, str] = skill_def.get("resources", {})
        for rpath, rcontent in resources.items():
            try:
                await skill_svc.write_resource(name, rpath, rcontent)
            except Exception:
                logger.debug("Failed to write resource '%s/%s'", name, rpath)

    return id_map


async def _create_subagents(
    bundled_subagents: list[dict],
    skill_id_map: dict[str, str],
) -> dict[str, str]:
    """Create Subagents and return old_id -> new_id mapping.

    Uses AgentService.get_agent_by_name for idempotent de-duplication.
    Remaps skill_ids using the provided mapping.
    """
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    id_map: dict[str, str] = {}

    for sub_def in bundled_subagents:
        original_id = sub_def.get("original_id", "")
        profile = sub_def.get("profile", {})
        name = profile.get("display_name") or "Imported Subagent"

        existing = await AgentService.get_agent_by_name(name)
        if existing:
            id_map[original_id] = existing.id
            continue

        old_skill_ids = profile.get("skill_ids", [])
        remapped_skill_ids = [skill_id_map.get(sid, sid) for sid in old_skill_ids]

        agent_data = AgentCreate(
            name=name,
            description=profile.get("description", ""),
            system_prompt=profile.get("system_prompt", ""),
            skill_ids=remapped_skill_ids,
            mcp_ids=profile.get("mcp_ids", []),
            mcp_tool_selections=profile.get("mcp_tool_selections"),
            enabled_builtin_tools=profile.get("enabled_builtin_tools", []),
            subagent_ids=[],
            is_built_in=False,
        )
        new_agent = await AgentService.create_agent(agent_data)
        id_map[original_id] = new_agent.id

    return id_map


def _remap_ids(
    profile: dict,
    skill_id_map: dict[str, str],
    subagent_id_map: dict[str, str],
) -> dict:
    """Remap old Skill/Subagent IDs to new local IDs."""
    remapped = dict(profile)

    old_skill_ids = remapped.get("skill_ids", [])
    remapped["skill_ids"] = [
        skill_id_map.get(sid, sid) for sid in old_skill_ids
    ]

    old_subagent_ids = remapped.get("subagent_ids", [])
    remapped["subagent_ids"] = [
        subagent_id_map.get(sid, sid) for sid in old_subagent_ids
    ]

    return remapped


async def _create_agent(profile: dict) -> str:
    """Create the main Agent from imported profile data."""
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    agent_data = AgentCreate(
        name=profile.get("display_name") or "Imported Agent",
        description=profile.get("description", ""),
        system_prompt=profile.get("system_prompt", ""),
        skill_ids=profile.get("skill_ids", []),
        mcp_ids=profile.get("mcp_ids", []),
        mcp_tool_selections=profile.get("mcp_tool_selections"),
        enabled_builtin_tools=profile.get("enabled_builtin_tools", []),
        subagent_ids=profile.get("subagent_ids", []),
        personality_style=profile.get("personality_style", "professional"),
        max_iterations=profile.get("max_iterations"),
        is_built_in=False,
    )
    new_agent = await AgentService.create_agent(agent_data)
    return new_agent.id
