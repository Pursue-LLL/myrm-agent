"""Dependency closure of one expert for export (business layer).

Collects everything the expert needs to work on another machine: sub-experts
(cycle-safe), the skills it uses (custom skills with their files, presets by name),
the connectors it uses (declarations without secrets) and its workspace templates.
Whatever cannot travel is recorded in ``ExportPlan.omitted`` instead of being dropped
silently, so the exporter can show a complete "not included" list.

[INPUT]
- app.services.agent.agent_service::AgentService (POS: stored experts.)
- app.core.skills.store.service::skills_service (POS: installed-skill catalog and files.)
- app.core.skills.packaging.collect::collect_skill_files (POS: exportable skill file tree.)
- app.services.config.service::config_service (POS: global ``mcpServers`` store.)
- .agent_surface::profile_to_plugin_agent (POS: disposition-table-driven expert projection.)
- ._export_connector::connector_from_config (POS: portable connector declaration.)
- .template_workspace::decode_template_files (POS: stored workspace templates.)

[OUTPUT]
- build_export_plan: expert id -> ExportPlan (raises ExportError for unknown or built-in experts).
- MAX_EXPORT_EXPERTS / MAX_SKILL_FILE_BYTES / MAX_EXPORT_TEXT_BYTES: export capacity ceilings.

[POS]
Read-only collector. Redaction, packaging and the HTTP contract live elsewhere.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.plugins.models import PluginMcpServer
from myrm_agent_harness.agent.plugins.rules import (
    MAX_TEMPLATE_FILE_BYTES,
    MAX_TOTAL_TEMPLATE_BYTES,
    is_excluded_path,
    is_valid_plugin_name,
    plugin_identity,
)
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.backends.profiles.types import AgentProfile
from myrm_agent_harness.toolkits.storage.types import SkillType

from ._export_connector import connector_from_config
from ._export_models import (
    ExpertDraft,
    ExportedSkill,
    ExportError,
    ExportErrorCode,
    ExportPlan,
    Omit,
    OmittedItem,
    OmittedKind,
)
from ._preview_context import expert_key
from .agent_surface import MAX_NAME_CHARS, carried_max_iterations, profile_to_plugin_agent
from .template_workspace import TEMPLATE_FILES_KEY, decode_template_files

if TYPE_CHECKING:
    from app.core.skills.models import Skill

__all__ = ["MAX_EXPORT_EXPERTS", "MAX_EXPORT_TEXT_BYTES", "MAX_SKILL_FILE_BYTES", "build_export_plan"]

logger = logging.getLogger(__name__)

MAX_EXPORT_EXPERTS = 25
MAX_SKILL_FILE_BYTES = 1024 * 1024
# Every shipped text file is scanned for secrets (~1 s/MB), so the reviewed corpus is bounded.
MAX_EXPORT_TEXT_BYTES = 10 * 1024 * 1024
_MAX_ORIGIN_CHARS = 64


async def build_export_plan(agent_id: str) -> ExportPlan:
    """Collect the dependency closure of the expert ``agent_id``."""
    from app.services.agent.agent_service import AgentService

    root = await AgentService.get_agent_by_id(agent_id)
    if root is None:
        raise ExportError(ExportErrorCode.EXPERT_NOT_FOUND, "Expert not found")
    if root.built_in:
        raise ExportError(ExportErrorCode.BUILT_IN_EXPERT, "Built-in experts cannot be exported")

    collector = _Collector(await _load_catalog(), await _load_servers())
    await collector.walk(root)
    return await collector.finish(root)


@dataclass(frozen=True)
class _Catalog:
    by_id: Mapping[str, Skill]
    by_name: Mapping[str, Skill]

    def find(self, ref: str) -> Skill | None:
        """Experts reference skills by id; names are accepted for bindings made from skill folder names."""
        return self.by_id.get(ref) or self.by_name.get(ref.strip().lower())


async def _load_catalog() -> _Catalog:
    from app.core.skills.store.service import skills_service

    skills = await skills_service.list_skills()
    # Presets are assigned last so a preset wins over a local copy of the same name.
    return _Catalog(
        by_id={skill.id: skill for skill in skills},
        by_name={skill.name.lower(): skill for skill in sorted(skills, key=lambda s: s.type == SkillType.PREBUILT)},
    )


async def _load_servers() -> dict[str, dict[str, object]]:
    from app.services.config.service import config_service

    from ._mcp_persist import _load_persisted_mcp_configs

    configs = await _load_persisted_mcp_configs(config_service)
    return {str(cfg["name"]).strip(): cfg for cfg in configs if str(cfg.get("name", "")).strip()}


class _Collector:
    def __init__(self, catalog: _Catalog, servers: Mapping[str, dict[str, object]]) -> None:
        self._catalog = catalog
        self._servers = servers
        self._profiles: dict[str, AgentProfile] = {}  # discovery order; the entry expert first
        self._children: dict[str, list[str]] = {}
        self._skill_refs: dict[str, str | None] = {}  # skill id -> name experts reference it by (None: not shipped)
        self._skills: dict[str, ExportedSkill] = {}
        self._preset_names: dict[str, None] = {}
        self._connectors: dict[str, PluginMcpServer] = {}
        self._seen_connectors: set[str] = set()
        self._text_bytes = 0
        self._omitted: list[OmittedItem] = []

    def _omit(self, kind: OmittedKind, name: str, reason: Omit, owner: str | None = None) -> None:
        self._omitted.append(OmittedItem(kind, name, reason, owner))

    async def walk(self, profile: AgentProfile, ancestors: tuple[str, ...] = ()) -> None:
        """Depth-first over sub-experts; a link back to an ancestor is dropped (that is the only way to loop)."""
        from app.services.agent.agent_service import AgentService

        self._profiles[profile.id] = profile
        lineage = (*ancestors, profile.id)
        owner = _label(profile)
        kept: list[str] = []
        for child_id in _strings((profile.metadata or {}).get("subagent_ids")):
            if child_id in lineage:
                self._omit("expert", child_id, Omit.EXPERT_CYCLE, owner)
            elif child_id in self._profiles:
                kept.append(child_id)
            elif (child := await AgentService.get_agent_by_id(child_id)) is None:
                self._omit("expert", child_id, Omit.EXPERT_MISSING, owner)
            elif child.built_in:
                self._omit("expert", _label(child), Omit.EXPERT_BUILT_IN, owner)
            elif len(self._profiles) >= MAX_EXPORT_EXPERTS:
                self._omit("expert", _label(child), Omit.TOO_MANY_EXPERTS, owner)
            else:
                kept.append(child_id)
                await self.walk(child, lineage)
        self._children[profile.id] = kept

    async def finish(self, root: AgentProfile) -> ExportPlan:
        names = _unique_names(self._profiles.values())
        drafts: list[ExpertDraft] = []
        for index, profile in enumerate(self._profiles.values()):
            owner = names[profile.id]
            agent = profile_to_plugin_agent(
                profile,
                skill_names=await self._bind_skills(profile, owner),
                mcp_names=self._bind_connectors(profile, owner),
                subagent_names=tuple(names[child] for child in self._children[profile.id]),
                is_subagent=index > 0,
                is_entry_agent=index == 0,
            )
            drafts.append(ExpertDraft(profile.id, replace(agent, name=owner)))
            self._report_unshared(profile, owner, is_entry=index == 0)

        return ExportPlan(
            plugin_name=plugin_identity(names[root.id], fallback="myrm-expert"),
            experts=drafts,
            skills=list(self._skills.values()),
            preset_skill_names=list(self._preset_names),
            connectors=list(self._connectors.values()),
            workspace_files=self._workspace(root, names[root.id]),
            omitted=self._omitted,
        )

    # -- skills ---------------------------------------------------------------------------------

    async def _bind_skills(self, profile: AgentProfile, owner: str) -> tuple[str, ...]:
        refs: dict[str, None] = {}
        for ref in profile.skills or []:
            name = await self._skill_reference(ref, owner)
            if name:
                refs[name] = None
        return tuple(refs)

    async def _skill_reference(self, ref: str, owner: str) -> str | None:
        skill = self._catalog.find(ref)
        if skill is None:
            self._omit("skill", ref, Omit.SKILL_UNAVAILABLE, owner)
            return None
        if skill.type == SkillType.PREBUILT:
            self._preset_names.setdefault(skill.name)
            return skill.name
        if skill.id not in self._skill_refs:
            self._skill_refs[skill.id] = await self._ship_skill(skill, owner)
        return self._skill_refs[skill.id]

    async def _ship_skill(self, skill: Skill, owner: str) -> str | None:
        from app.core.skills.packaging.collect import collect_skill_files
        from app.core.skills.store.service import skills_service

        package_name = self._package_name(skill)
        try:
            collected = await collect_skill_files(skills_service, skill.id)
        except Exception as exc:
            logger.warning("Skill %s could not be read for export: %s", skill.id, exc)
            collected = {}

        files: dict[str, bytes] = {}
        for rel, content in sorted(collected.items()):
            reason = _rejection(rel, content, limit=MAX_SKILL_FILE_BYTES, room=MAX_EXPORT_TEXT_BYTES - self._text_bytes)
            if reason is not None:
                self._omit("skill_file", f"{package_name}/{rel}", reason, skill.name)
                continue
            self._text_bytes += len(content)
            files[rel] = content

        if SKILL_MD_FILE not in files:
            self._omit("skill", skill.name, Omit.SKILL_UNAVAILABLE, owner)
            return None
        source = (skill.installed_from or {}).get("source")
        self._skills[package_name] = ExportedSkill(
            package_name=package_name,
            display_name=skill.name,
            version=skill.version or None,
            origin_source=source.strip()[:_MAX_ORIGIN_CHARS] if isinstance(source, str) and source.strip() else None,
            files=files,
        )
        return package_name

    def _package_name(self, skill: Skill) -> str:
        physical = Path(skill.storage_path).name
        base = physical if is_valid_plugin_name(physical) else plugin_identity(skill.name, fallback="skill")
        name, attempt = base, 1
        while name in self._skills:
            attempt += 1
            name = f"{base}-{attempt}"
        return name

    # -- connectors -----------------------------------------------------------------------------

    def _bind_connectors(self, profile: AgentProfile, owner: str) -> tuple[str, ...]:
        names: dict[str, None] = {}
        for name in _strings((profile.metadata or {}).get("mcp_ids")):
            if name not in self._seen_connectors:
                self._seen_connectors.add(name)
                self._load_connector(name, owner)
            if name in self._connectors:
                names[name] = None
        return tuple(names)

    def _load_connector(self, name: str, owner: str) -> None:
        cfg = self._servers.get(name)
        if cfg is None:
            self._omit("connector", name, Omit.CONNECTOR_MISSING, owner)
            return
        outcome = connector_from_config(cfg)
        if outcome.server is None:
            self._omit("connector", name, outcome.omit or Omit.CONNECTOR_UNSUPPORTED, owner)
            return
        self._connectors[name] = outcome.server

    # -- workspace templates and unshared settings ------------------------------------------------

    def _workspace(self, root: AgentProfile, owner: str) -> dict[str, bytes]:
        kept: dict[str, bytes] = {}
        template_bytes = 0
        for rel, content in sorted(_template_files(root).items()):
            room = min(MAX_TOTAL_TEMPLATE_BYTES - template_bytes, MAX_EXPORT_TEXT_BYTES - self._text_bytes)
            reason = _rejection(rel, content, limit=MAX_TEMPLATE_FILE_BYTES, room=room)
            if reason is not None:
                self._omit("workspace_file", rel, reason, owner)
                continue
            template_bytes += len(content)
            self._text_bytes += len(content)
            kept[rel] = content
        return kept

    def _report_unshared(self, profile: AgentProfile, owner: str, *, is_entry: bool) -> None:
        meta = profile.metadata or {}
        for setting in ("openapi_services", "tool_gateway_config"):
            if meta.get(setting):
                self._omit("setting", setting, Omit.MAY_CARRY_CREDENTIALS, owner)
        if profile.max_iterations is not None and carried_max_iterations(profile.max_iterations) is None:
            self._omit("setting", "max_iterations", Omit.ABOVE_DEFAULT, owner)
        if not is_entry and _template_files(profile):
            self._omit("setting", "workspace_templates", Omit.SUB_EXPERT_WORKSPACE, owner)


def _rejection(rel: str, content: bytes, *, limit: int, room: int) -> Omit | None:
    """Why a file cannot ship (None: it can). ``room`` is what is left of the group's byte budget."""
    if not _is_shippable_path(rel):
        return Omit.EXCLUDED_PATH
    if len(content) > limit:
        return Omit.OVERSIZED_FILE
    if not _is_text(content):
        return Omit.BINARY_FILE
    if len(content) > room:
        return Omit.TOTAL_SIZE_EXCEEDED
    return None


def _is_shippable_path(rel: str) -> bool:
    parts = rel.split("/")
    safe = bool(rel) and not rel.startswith(("/", "\\")) and ".." not in parts and "" not in parts and "\\" not in rel
    return safe and not is_excluded_path(rel)


def _is_text(content: bytes) -> bool:
    """Only text can be reviewed for secrets; anything else is left out."""
    if b"\0" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _template_files(profile: AgentProfile) -> dict[str, bytes]:
    engine = (profile.metadata or {}).get("engine_params")
    stored = engine.get(TEMPLATE_FILES_KEY) if isinstance(engine, dict) else None
    return decode_template_files(stored) if isinstance(stored, dict) else {}


def _unique_names(profiles: Iterable[AgentProfile]) -> dict[str, str]:
    """Package-level expert names; experts reference each other by name, so they must not collide."""
    taken: set[str] = set()
    names: dict[str, str] = {}
    for profile in profiles:
        base = _label(profile)[:MAX_NAME_CHARS]
        candidate, attempt = base, 1
        while expert_key(candidate) in taken:
            attempt += 1
            candidate = f"{base} ({attempt})"
        taken.add(expert_key(candidate))
        names[profile.id] = candidate
    return names


def _label(profile: AgentProfile) -> str:
    return (profile.display_name or "").strip() or profile.id


def _strings(value: object) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []
