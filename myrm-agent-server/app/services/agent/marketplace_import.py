"""Marketplace import — install Agent profile from marketplace package.

Takes a marketplace package (exported via marketplace_export) and creates
the Agent plus all missing dependencies in the local sandbox. Skills are
created via SkillCreationService; Agents are persisted via AgentService.

[INPUT]
- core.skills.creation.service::SkillCreationService (POS: Skill 写入服务)
- services.agent.agent_service::AgentService (POS: Agent CRUD 服务)
- services.agent.marketplace_package_contract::validate_marketplace_package
  (POS: Marketplace 包契约与完整性校验)
- Marketplace package dict (from marketplace_export)

[OUTPUT]
- import_agent_package(skill_svc, package): Creates Agent + dependencies, returns new Agent ID
  with atomic rollback on failure

[POS]
Server-side import for marketplace install flow. Resolves Skill dependencies
via SkillCreationService, remaps Skill/Subagent IDs, enforces fail-closed package
contract/integrity gate, and guarantees atomic rollback when any import stage fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.agent.marketplace_package_contract import (
    MarketplaceBundledSkillContract,
    MarketplaceBundledSubagentContract,
    validate_marketplace_package,
)

if TYPE_CHECKING:
    from app.core.skills.creation.service import SkillCreationService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ImportMutationState:
    """Track created entities so import can rollback atomically on failure."""

    created_skill_names: list[str] = field(default_factory=list)
    created_subagent_ids: list[str] = field(default_factory=list)
    created_agent_id: str | None = None


async def import_agent_package(
    skill_svc: "SkillCreationService",
    package: dict[str, object],
) -> str:
    """Import a marketplace package into the local sandbox.

    Args:
        skill_svc: SkillCreationService for writing Skills to filesystem.
        package: Marketplace package dict from export.

    Returns:
        New Agent ID.
    """
    validated_package = validate_marketplace_package(package)
    agent_profile = validated_package.agent_profile.model_dump()
    bundled_skills = validated_package.bundled_skills
    bundled_subagents = validated_package.bundled_subagents

    _preflight_skill_name_conflicts(skill_svc, bundled_skills)

    state = _ImportMutationState()
    try:
        skill_id_map = await _install_skills(skill_svc, bundled_skills, state)
        subagent_id_map = await _create_subagents(bundled_subagents, skill_id_map, state)
        remapped_profile = _remap_ids(agent_profile, skill_id_map, subagent_id_map)
        new_agent_id = await _create_agent(remapped_profile)
        state.created_agent_id = new_agent_id
    except Exception as exc:
        rollback_errors = await _rollback_created_entities(skill_svc, state)
        if rollback_errors:
            raise RuntimeError(
                "Marketplace import failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise

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
    bundled_skills: list[MarketplaceBundledSkillContract],
    state: _ImportMutationState,
) -> dict[str, str]:
    """Install bundled Skills via SkillCreationService.

    Returns:
        Mapping of old skill ID -> new local skill ID.
    """
    id_map: dict[str, str] = {}

    for skill_def in bundled_skills:
        result = await skill_svc.save_skill(
            skill_def.name,
            skill_def.content,
            skill_def.description,
        )
        if _result_success(result) is not True:
            raise ValueError(
                f"Marketplace import rejected: failed to save skill '{skill_def.name}': "
                f"{_result_error(result)}"
            )

        was_updated = _result_bool(result, "was_updated")
        if was_updated is None:
            raise RuntimeError(
                "Marketplace import failed: skill backend did not return 'was_updated' "
                f"for '{skill_def.name}', cannot guarantee atomic rollback safety"
            )
        if was_updated is True:
            raise ValueError(
                f"Marketplace import rejected: skill '{skill_def.name}' already exists locally"
            )

        new_skill_id = _result_str(result, "skill_id")
        if not new_skill_id:
            raise RuntimeError(
                f"Marketplace import failed: skill '{skill_def.name}' returned empty skill_id"
            )
        id_map[skill_def.id] = new_skill_id
        state.created_skill_names.append(skill_def.name)

        for resource_path, resource_content in skill_def.resources.items():
            resource_result = await skill_svc.write_resource(
                skill_def.name,
                resource_path,
                resource_content,
            )
            if _result_success(resource_result) is not True:
                raise RuntimeError(
                    "Marketplace import failed: unable to write "
                    f"resource '{skill_def.name}/{resource_path}': {_result_error(resource_result)}"
                )

    return id_map


async def _create_subagents(
    bundled_subagents: list[MarketplaceBundledSubagentContract],
    skill_id_map: dict[str, str],
    state: _ImportMutationState,
) -> dict[str, str]:
    """Create Subagents and return old_id -> new_id mapping.

    Uses AgentService.get_agent_by_name for idempotent de-duplication.
    Remaps skill_ids using the provided mapping.
    """
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    id_map: dict[str, str] = {}

    for sub_def in bundled_subagents:
        profile = sub_def.profile
        name = profile.display_name

        existing = await AgentService.get_agent_by_name(name)
        if existing:
            id_map[sub_def.original_id] = existing.id
            continue

        remapped_skill_ids = [skill_id_map.get(sid, sid) for sid in profile.skill_ids]

        agent_data = AgentCreate(
            name=name,
            description=profile.description or "",
            system_prompt=profile.system_prompt or "",
            skill_ids=remapped_skill_ids,
            mcp_ids=profile.mcp_ids,
            mcp_tool_selections=profile.mcp_tool_selections,
            enabled_builtin_tools=profile.enabled_builtin_tools or [],
            subagent_ids=[],
            is_built_in=False,
        )
        new_agent = await AgentService.create_agent(agent_data)
        id_map[sub_def.original_id] = new_agent.id
        state.created_subagent_ids.append(new_agent.id)

    return id_map


def _remap_ids(
    profile: dict[str, object],
    skill_id_map: dict[str, str],
    subagent_id_map: dict[str, str],
) -> dict[str, object]:
    """Remap old Skill/Subagent IDs to new local IDs."""
    remapped = dict(profile)

    old_skill_ids_obj = remapped.get("skill_ids")
    old_skill_ids = old_skill_ids_obj if isinstance(old_skill_ids_obj, list) else []
    remapped["skill_ids"] = [
        skill_id_map.get(sid, sid) for sid in old_skill_ids
    ]

    old_subagent_ids_obj = remapped.get("subagent_ids")
    old_subagent_ids = old_subagent_ids_obj if isinstance(old_subagent_ids_obj, list) else []
    remapped["subagent_ids"] = [
        subagent_id_map.get(sid, sid) for sid in old_subagent_ids
    ]

    return remapped


async def _create_agent(profile: dict[str, object]) -> str:
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


def _result_bool(result: object, field_name: str) -> bool | None:
    value = getattr(result, field_name, None)
    return value if isinstance(value, bool) else None


def _result_success(result: object) -> bool | None:
    return _result_bool(result, "success")


def _result_error(result: object) -> str:
    value = getattr(result, "error", "")
    return value if isinstance(value, str) else ""


def _result_str(result: object, field_name: str) -> str:
    value = getattr(result, field_name, "")
    return value if isinstance(value, str) else ""


def _preflight_skill_name_conflicts(
    skill_svc: "SkillCreationService",
    bundled_skills: list[MarketplaceBundledSkillContract],
) -> None:
    base_path = getattr(skill_svc, "base_path", None)
    if not isinstance(base_path, Path):
        return

    conflicts: list[str] = []
    for skill in bundled_skills:
        if (base_path / skill.name / "SKILL.md").exists():
            conflicts.append(skill.name)
    if conflicts:
        conflict_text = ", ".join(sorted(conflicts))
        raise ValueError(
            "Marketplace import rejected: bundled skills already exist locally: "
            f"{conflict_text}"
        )


async def _rollback_created_entities(
    skill_svc: "SkillCreationService",
    state: _ImportMutationState,
) -> list[str]:
    from app.services.agent.agent_service import AgentService

    errors: list[str] = []

    if state.created_agent_id:
        try:
            deleted = await AgentService.delete_agent(state.created_agent_id)
            if not deleted:
                errors.append(f"delete agent {state.created_agent_id} returned False")
        except Exception as exc:  # pragma: no cover - defensive logging path
            errors.append(f"delete agent {state.created_agent_id} failed: {exc}")

    for subagent_id in reversed(state.created_subagent_ids):
        try:
            deleted = await AgentService.delete_agent(subagent_id)
            if not deleted:
                errors.append(f"delete subagent {subagent_id} returned False")
        except Exception as exc:  # pragma: no cover - defensive logging path
            errors.append(f"delete subagent {subagent_id} failed: {exc}")

    for skill_name in reversed(state.created_skill_names):
        try:
            result = await skill_svc.delete_skill(skill_name)
            if _result_success(result) is not True:
                errors.append(
                    f"delete skill {skill_name} failed: {_result_error(result) or 'unknown error'}"
                )
        except Exception as exc:  # pragma: no cover - defensive logging path
            errors.append(f"delete skill {skill_name} raised: {exc}")

    if errors:
        logger.error("Marketplace import rollback incomplete: %s", "; ".join(errors))
    return errors
