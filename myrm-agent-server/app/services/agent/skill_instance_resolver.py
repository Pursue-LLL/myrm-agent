"""Resolve Agent-bound skill instance names for runtime env + L1 footer SSOT.

[INPUT]
- myrm_agent_harness.backends.skills.state_manager::SkillStateManager (POS: instance storage)

[OUTPUT]
- resolve_skill_instance_bindings: skill_name -> instance_name map for harness default_skill_instances
- resolve_runtime_skill_instance_bindings: runtime_skill_ids + skill_configs → same map (factory SSOT)
- validate_agent_skill_config_instances: reject Agent save when skill_configs.instance_name is invalid (400)
- serialize_agent_skill_configs: normalize dict or Pydantic SkillConfig entries to JSON-safe dicts before DB persist

[POS]
Server business layer. Maps Agent profile skill_configs.instance_name to persisted instances.
Harness consumes the result via factory.py — no harness coupling to Agent DB.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.state_manager import SkillStateManager

logger = logging.getLogger(__name__)

_DEFAULT_INSTANCE_NAME = "default"


class SkillConfigValidationError(ValueError):
    """Raised when Agent skill_configs.instance_name does not match a persisted instance."""

    def __init__(self, skill_id: str, instance_name: str, skill_name: str) -> None:
        self.skill_id = skill_id
        self.instance_name = instance_name
        self.skill_name = skill_name
        super().__init__(
            f"Skill instance '{instance_name}' not found for skill '{skill_name}' (id={skill_id})"
        )


def _coerce_instance_name(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name if name else None


def _instance_name_from_skill_config(cfg: object) -> str | None:
    """Read instance_name from Agent skill_configs entry (dict or Pydantic SkillConfig)."""
    if isinstance(cfg, dict):
        return _coerce_instance_name(cfg.get("instance_name"))
    instance_name = getattr(cfg, "instance_name", None)
    return _coerce_instance_name(instance_name)


def serialize_agent_skill_configs(
    skill_configs: dict[str, object] | None,
) -> dict[str, dict[str, object]] | None:
    """Normalize Agent skill_configs to JSON-serializable dicts for DB persist."""
    if skill_configs is None:
        return None
    serialized: dict[str, dict[str, object]] = {}
    for skill_id, cfg in skill_configs.items():
        if isinstance(cfg, dict):
            serialized[skill_id] = {
                "is_core": bool(cfg.get("is_core", False)),
                "instance_name": _coerce_instance_name(cfg.get("instance_name")),
            }
            continue
        model_dump = getattr(cfg, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json")
            if isinstance(dumped, dict):
                serialized[skill_id] = {
                    "is_core": bool(dumped.get("is_core", False)),
                    "instance_name": _coerce_instance_name(dumped.get("instance_name")),
                }
    return serialized


def _pick_auto_instance(instances: list[str]) -> str | None:
    if len(instances) == 1:
        return instances[0]
    if _DEFAULT_INSTANCE_NAME in instances:
        return _DEFAULT_INSTANCE_NAME
    return None


def resolve_skill_instance_bindings(
    *,
    target_skill_names: list[str],
    skill_configs: dict[str, dict] | None,
    skill_id_to_name: dict[str, str],
    state_manager: SkillStateManager,
) -> dict[str, str]:
    """Resolve skill_name -> instance_name bindings for an Agent runtime.

    Priority per skill:
    1. agent.skill_configs[skill_id].instance_name when valid
    2. exactly one persisted instance
    3. instance named \"default\" when present
    4. no binding
    """
    explicit_by_name: dict[str, str] = {}
    if skill_configs:
        for skill_id, cfg in skill_configs.items():
            instance_name = _instance_name_from_skill_config(cfg)
            if instance_name is None:
                continue
            skill_name = skill_id_to_name.get(skill_id, skill_id)
            explicit_by_name[skill_name] = instance_name

    bindings: dict[str, str] = {}
    seen: set[str] = set()

    for skill_name in target_skill_names:
        if not skill_name or skill_name in seen:
            continue
        seen.add(skill_name)

        instances = state_manager.list_instances(skill_name)

        if skill_name in explicit_by_name:
            chosen = explicit_by_name[skill_name]
            if chosen in instances:
                bindings[skill_name] = chosen
                continue
            logger.warning(
                "Agent bound instance '%s' not found for skill '%s'; falling back to auto",
                chosen,
                skill_name,
            )

        auto = _pick_auto_instance(instances)
        if auto is not None:
            bindings[skill_name] = auto

    return bindings


def resolve_runtime_skill_instance_bindings(
    *,
    runtime_skill_ids: list[str],
    skill_configs: dict[str, dict] | None,
    skill_id_to_name: dict[str, str],
    state_manager: SkillStateManager,
) -> dict[str, str]:
    """Resolve bindings for an Agent runtime skill allowlist (factory SSOT wiring)."""
    target_skill_names: list[str] = []
    for skill_id in runtime_skill_ids or []:
        mapped = skill_id_to_name.get(skill_id)
        if mapped and mapped not in target_skill_names:
            target_skill_names.append(mapped)

    return resolve_skill_instance_bindings(
        target_skill_names=target_skill_names,
        skill_configs=skill_configs,
        skill_id_to_name=skill_id_to_name,
        state_manager=state_manager,
    )


async def build_skill_id_to_name_map() -> dict[str, str]:
    """Map skill storage IDs and names to runtime skill names (factory-aligned)."""
    from app.core.skills.store import skills_service

    skill_id_to_name: dict[str, str] = {}
    for skill in await skills_service.list_skills():
        skill_id_to_name[skill.id] = skill.name
        skill_id_to_name[skill.name] = skill.name
    return skill_id_to_name


async def validate_agent_skill_config_instances(
    *,
    skill_configs: dict[str, object] | None,
    state_manager: SkillStateManager | None = None,
    skill_id_to_name: dict[str, str] | None = None,
) -> None:
    """Validate explicit Agent skill_configs.instance_name bindings before persist."""
    if not skill_configs:
        return

    from app.core.skills.state_manager_instance import get_state_manager

    manager = state_manager or get_state_manager()
    id_to_name = skill_id_to_name if skill_id_to_name is not None else await build_skill_id_to_name_map()

    for skill_id, cfg in skill_configs.items():
        instance_name = _instance_name_from_skill_config(cfg)
        if instance_name is None:
            continue
        skill_name = id_to_name.get(skill_id, skill_id)
        instances = manager.list_instances(skill_name)
        if instance_name not in instances:
            raise SkillConfigValidationError(skill_id, instance_name, skill_name)
