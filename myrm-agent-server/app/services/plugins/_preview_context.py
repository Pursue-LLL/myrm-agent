"""Installation state a plugin import is previewed and confirmed against (business layer).

Preview flags (conflicts, unresolved references, deployment blocks) and confirm
decisions must read the same facts, so both load them through ``load_preview_context``.
Confirm re-queries it instead of trusting preview-time flags.

[INPUT]
- app.core.skills.store.service::skills_service (POS: installed skill catalog, local + preset.)
- app.services.config.service::config_service (POS: global ``mcpServers`` store.)
- app.services.agent.agent_service::AgentService (POS: same-name expert lookup.)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities (POS: deployment limits.)
- app.config.settings::settings (POS: ``mcp.allow_stdio`` cloud switch.)

[OUTPUT]
- ExistingSkill: an installed local skill under a package skill's name (version and install source for the conflict card).
- ExistingExpert: an expert already present under a package expert's name.
- PreviewContext: immutable snapshot of installed skills, connectors, experts and deployment limits.
- load_preview_context: gather the snapshot (failures degrade to empty facts, never block a preview).

[POS]
Read-only fact gathering for plugin import preview/confirm.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = ["ExistingExpert", "ExistingSkill", "PreviewContext", "expert_key", "load_preview_context"]


def expert_key(name: str) -> str:
    """Same-name key of experts (case-insensitive, matches ``AgentService`` lookups)."""
    return name.strip().casefold()


@dataclass(frozen=True)
class ExistingSkill:
    skill_id: str
    version: str | None
    source: str | None  # install provenance label (``origin.json`` source), None for hand-made skills


@dataclass(frozen=True)
class ExistingExpert:
    agent_id: str
    is_built_in: bool


@dataclass(frozen=True)
class PreviewContext:
    skill_ids_by_name: Mapping[str, str] = field(default_factory=dict)  # lowercase name -> skill id (local + preset)
    local_skills: Mapping[str, ExistingSkill] = field(default_factory=dict)  # lowercase name -> installed local skill
    server_names: frozenset[str] = frozenset()  # connectors already configured
    experts_by_name: Mapping[str, ExistingExpert] = field(default_factory=dict)  # expert_key(name) -> match
    allows_local_skills: bool = True
    allow_stdio: bool = True

    @property
    def local_skill_names(self) -> frozenset[str]:
        """Lowercase names of installed local skills (the conflict basis)."""
        return frozenset(self.local_skills)


async def load_preview_context(agent_names: Sequence[str] = ()) -> PreviewContext:
    """Snapshot the installation state relevant to a package carrying ``agent_names``."""
    skill_ids_by_name, local_skills = await _load_skills()
    return PreviewContext(
        skill_ids_by_name=skill_ids_by_name,
        local_skills=local_skills,
        server_names=await _load_server_names(),
        experts_by_name=await _load_experts(agent_names),
        allows_local_skills=_allows_local_skills(),
        allow_stdio=_allows_stdio(),
    )


async def _load_skills() -> tuple[dict[str, str], dict[str, ExistingSkill]]:
    from app.core.skills.store.service import skills_service

    try:
        skills = await skills_service.list_skills()
    except Exception as exc:
        logger.warning("Failed to list installed skills for plugin import: %s", exc)
        return {}, {}

    ids_by_name: dict[str, str] = {}
    local_skills: dict[str, ExistingSkill] = {}
    # A package referencing a skill it does not bundle means the preset: presets win over local copies.
    for skill in sorted(skills, key=lambda s: s.id.startswith("local::"), reverse=True):
        ids_by_name[skill.name.lower()] = skill.id
        if skill.id.startswith("local::"):
            origin_source = (skill.installed_from or {}).get("source")
            local_skills[skill.name.lower()] = ExistingSkill(
                skill_id=skill.id,
                version=skill.version or None,
                source=origin_source if isinstance(origin_source, str) and origin_source else None,
            )
    return ids_by_name, local_skills


async def _load_server_names() -> frozenset[str]:
    from app.services.config.service import config_service

    from ._mcp_persist import _load_persisted_mcp_configs

    configs = await _load_persisted_mcp_configs(config_service)
    return frozenset(str(cfg.get("name", "")) for cfg in configs if cfg.get("name"))


async def _load_experts(agent_names: Sequence[str]) -> dict[str, ExistingExpert]:
    from app.services.agent.agent_service import AgentService

    experts: dict[str, ExistingExpert] = {}
    for name in agent_names:
        key = expert_key(name)
        if not key or key in experts:
            continue
        try:
            matches = await AgentService.get_agents_by_name(name)
        except Exception as exc:
            logger.warning("Failed to look up expert %r for plugin import: %s", name, exc)
            continue
        if matches:
            # get_agents_by_name sorts user-created experts before built-ins
            experts[key] = ExistingExpert(agent_id=matches[0].id, is_built_in=bool(matches[0].built_in))
    return experts


def _allows_local_skills() -> bool:
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    return get_deployment_capabilities().allows_local_skills


def _allows_stdio() -> bool:
    from app.config.settings import settings

    return bool(settings.mcp.allow_stdio)
