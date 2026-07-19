"""Marketplace import — install Agent profile from marketplace package.

Takes a marketplace package (exported via marketplace_export) and creates
the Agent plus all missing dependencies in the local sandbox. Skills are
created via SkillCreationService; Agents are persisted via AgentService.

[INPUT]
- core.skills.creation.service::SkillCreationService (POS: Skill 写入服务)
- services.agent.agent_service::AgentService (POS: Agent CRUD 服务)
- services.agent.marketplace.package_contract::validate_marketplace_package
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
from typing import TYPE_CHECKING, Mapping

from app.services.agent.marketplace.package_contract import (
    MarketplaceBundledSkillContract,
    MarketplaceBundledSubagentContract,
    validate_marketplace_package,
)

if TYPE_CHECKING:
    from app.core.skills.creation.service import SkillCreationService

logger = logging.getLogger(__name__)
_SUBAGENT_ORIGIN_ENGINE_PARAM_KEY = "marketplace_subagent_origin_key"
_MARKETPLACE_ENTRY_ENGINE_PARAM_KEY = "marketplace_entry_id"


@dataclass(slots=True)
class _ImportMutationState:
    """Track created entities so import can rollback atomically on failure."""

    created_skill_names: list[str] = field(default_factory=list)
    created_subagent_ids: list[str] = field(default_factory=list)
    created_agent_id: str | None = None


async def import_agent_package(
    skill_svc: "SkillCreationService",
    package: dict[str, object],
    *,
    require_transport_signature: bool = False,
    transport_secret: str | None = None,
    marketplace_entry_id: str | None = None,
) -> str:
    """Import a marketplace package into the local sandbox.

    Args:
        skill_svc: SkillCreationService for writing Skills to filesystem.
        package: Marketplace package dict from export.

    Returns:
        New Agent ID.
    """
    validated_package = validate_marketplace_package(
        package,
        require_transport_signature=require_transport_signature,
        transport_secret=transport_secret,
    )
    normalized_entry_id = _normalize_marketplace_entry_id(marketplace_entry_id)
    agent_profile = validated_package.agent_profile.model_dump()
    bundled_skills = validated_package.bundled_skills
    bundled_subagents = validated_package.bundled_subagents
    package_payload_sha256 = validated_package.trust.payload_sha256

    _preflight_skill_name_conflicts(skill_svc, bundled_skills)

    state = _ImportMutationState()
    try:
        skill_id_map = await _install_skills(skill_svc, bundled_skills, state)
        subagent_id_map = await _create_subagents(
            bundled_subagents,
            skill_id_map,
            package_payload_sha256,
            state,
        )
        remapped_profile = _remap_ids(agent_profile, skill_id_map, subagent_id_map)
        new_agent_id = await _create_agent(
            remapped_profile,
            marketplace_entry_id=normalized_entry_id,
        )
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
    package_payload_sha256: str,
    state: _ImportMutationState,
) -> dict[str, str]:
    """Create Subagents and return old_id -> new_id mapping.

    Uses stable marketplace origin keys for de-duplication to avoid
    name-collision misbinding across unrelated packages.
    """
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    id_map: dict[str, str] = {}
    origin_index = await _load_subagent_origin_index()

    for sub_def in bundled_subagents:
        profile = sub_def.profile
        name = profile.display_name
        remapped_skill_ids = [skill_id_map.get(sid, sid) for sid in profile.skill_ids]
        origin_key = _build_subagent_origin_key(
            package_payload_sha256=package_payload_sha256,
            original_subagent_id=sub_def.original_id,
        )

        existing_id = await _find_existing_subagent_by_origin_key(
            origin_key,
            origin_index=origin_index,
        )
        if existing_id is not None:
            id_map[sub_def.original_id] = existing_id
            continue

        raw_profile = profile.model_dump()
        raw_profile["skill_ids"] = remapped_skill_ids
        raw_profile["engine_params"] = _with_subagent_origin_key(
            raw_profile.get("engine_params"),
            origin_key,
        )
        agent_payload = _agent_create_payload_from_profile(
            raw_profile,
            fallback_name=name,
            is_subagent=True,
        )
        agent_data = AgentCreate.model_validate(agent_payload)
        new_agent = await AgentService.create_agent(agent_data)
        id_map[sub_def.original_id] = new_agent.id
        state.created_subagent_ids.append(new_agent.id)
        origin_index[origin_key] = new_agent.id

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


async def _create_agent(
    profile: dict[str, object],
    *,
    marketplace_entry_id: str | None = None,
) -> str:
    """Create the main Agent from imported profile data."""
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    profile_payload = dict(profile)
    profile_payload["engine_params"] = _with_marketplace_entry_id(
        profile_payload.get("engine_params"),
        marketplace_entry_id,
    )
    agent_payload = _agent_create_payload_from_profile(
        profile_payload,
        fallback_name="Imported Agent",
        is_subagent=False,
    )
    agent_data = AgentCreate.model_validate(agent_payload)
    new_agent = await AgentService.create_agent(agent_data)
    return new_agent.id


def _agent_create_payload_from_profile(
    profile: Mapping[str, object],
    *,
    fallback_name: str,
    is_subagent: bool,
) -> dict[str, object]:
    display_name = profile.get("display_name")
    resolved_name = display_name if isinstance(display_name, str) and display_name.strip() else fallback_name
    payload: dict[str, object] = {
        "name": resolved_name,
        "description": profile.get("description") or "",
        "system_prompt": profile.get("system_prompt") or "",
        "skill_ids": profile.get("skill_ids", []),
        "mcp_ids": profile.get("mcp_ids", []),
        "mcp_tool_selections": profile.get("mcp_tool_selections"),
        "enabled_builtin_tools": profile.get("enabled_builtin_tools"),
        "subagent_ids": [] if is_subagent else profile.get("subagent_ids", []),
        "personality_style": profile.get("personality_style", "professional"),
        "max_iterations": profile.get("max_iterations"),
        "is_built_in": False,
    }

    model_selection = _derive_model_selection_payload(profile)
    if model_selection is not None:
        payload["model_selection"] = model_selection

    for optional_key in (
        "skill_configs",
        "security_overrides",
        "workspace_policy",
        "memory_policy",
        "engine_params",
        "auto_restore_domains",
        "openapi_services",
        "command_bindings",
        "prompt_mode",
        "agent_type",
        "allow_discovery",
        "notify_targets",
        "browser_source",
        "dialog_policy",
        "session_recording",
        "cron_post_run_verify",
        "suggestion_prompts",
        "home_directory",
    ):
        if optional_key in profile:
            value = profile[optional_key]
            if value is not None:
                payload[optional_key] = value

    if is_subagent:
        payload["subagent_ids"] = []
        payload["agent_type"] = "individual"

    return payload


def _derive_model_selection_payload(profile: Mapping[str, object]) -> dict[str, object] | None:
    raw_model_selection = profile.get("model_selection")
    if isinstance(raw_model_selection, dict):
        model_value = raw_model_selection.get("model")
        if isinstance(model_value, str) and model_value.strip():
            return raw_model_selection

    model_value = profile.get("model")
    if isinstance(model_value, str) and model_value.strip():
        return {
            "providerId": "auto",
            "model": model_value.strip(),
        }
    return None


def _build_subagent_origin_key(
    *,
    package_payload_sha256: str,
    original_subagent_id: str,
) -> str:
    return f"{package_payload_sha256}:{original_subagent_id}"


def _with_subagent_origin_key(
    engine_params: object,
    origin_key: str,
) -> dict[str, object]:
    merged: dict[str, object] = (
        dict(engine_params)
        if isinstance(engine_params, dict)
        else {}
    )
    merged[_SUBAGENT_ORIGIN_ENGINE_PARAM_KEY] = origin_key
    return merged


def _normalize_marketplace_entry_id(entry_id: str | None) -> str | None:
    if entry_id is None:
        return None
    normalized = entry_id.strip()
    if not normalized:
        raise ValueError("marketplace_entry_id must be a non-empty string when provided")
    return normalized


def _with_marketplace_entry_id(
    engine_params: object,
    marketplace_entry_id: str | None,
) -> dict[str, object] | None:
    if marketplace_entry_id is None:
        if isinstance(engine_params, dict):
            return dict(engine_params)
        return None
    merged: dict[str, object] = (
        dict(engine_params)
        if isinstance(engine_params, dict)
        else {}
    )
    merged[_MARKETPLACE_ENTRY_ENGINE_PARAM_KEY] = marketplace_entry_id
    return merged


async def _find_existing_subagent_by_origin_key(
    origin_key: str,
    *,
    origin_index: Mapping[str, str] | None = None,
) -> str | None:
    if origin_index is not None:
        return origin_index.get(origin_key)

    loaded_origin_index = await _load_subagent_origin_index()
    return loaded_origin_index.get(origin_key)


async def _load_subagent_origin_index() -> dict[str, str]:
    from app.database.repositories.uow import UnitOfWork

    async with UnitOfWork() as uow:
        profiles = await uow.agent_repo.list_profiles()

    index: dict[str, str] = {}
    for profile in profiles:
        metadata = profile.metadata
        if not isinstance(metadata, dict):
            continue
        engine_params = metadata.get("engine_params")
        if not isinstance(engine_params, dict):
            continue
        candidate = engine_params.get(_SUBAGENT_ORIGIN_ENGINE_PARAM_KEY)
        if isinstance(candidate, str) and candidate:
            index[candidate] = profile.id
    return index


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
