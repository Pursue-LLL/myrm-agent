"""Agent Plugins 1.0.0 import orchestration (business layer).

Consumes the framework-level parser (`myrm_agent_harness.agent.plugins`) and
persists components:
  - skills → SkillStore (INSTALLED trust layer, blue-green atomic write)
  - MCP servers → global ``mcpServers`` UserConfig (disabled by default)
  - Agent binding → `mcp_ids` + `skill_ids` on the target Agent profile

The import is fully offline (no LLM calls) and applies per-component failure
isolation so a single invalid skill or MCP server never aborts the whole import.
Skills whose name already exists in the store are upgraded in place (reusing the
existing ``skill_id`` with DERIVED lineage) instead of creating a duplicate, so
the skill library never accumulates same-name records.

[INPUT]
- myrm_agent_harness.agent.plugins.parser::AgentPluginParser (POS: framework
  plugin archive parser.)
- myrm_agent_harness.agent.skills.evolution.core.types (POS: skill lineage types.)
- myrm_agent_harness.agent.skills.evolution.db.store::SkillStore (POS: SQLite
  skill persistence; MAX_SKILL_CONTENT_CHARS is the oversized-content SSOT.)
- ._models::PluginImportSession, PluginConfirmItem (POS: business-layer DTOs.)
- ._staging::PluginStaging (POS: import session staging persistence.)
- ._mcp_persist (POS: MCP/agent persistence for plugin imports.)

[OUTPUT]
- build_preview_result: component preview payload with name-conflict flags.
- confirm_plugin_import: Persist skills, MCP servers, and agent bindings from a
  parsed plugin archive (offline, per-component failure isolation); returns
  imported/skipped counts plus ``required_secret_keys`` for the UI to guide
  secret configuration. Bundled plugin files are persisted via
  ``._plugin_files.persist_plugin_files`` and their roots embedded into
  ``extra_params`` (plugin_root / data_root).
- list_installed_plugins: provenance-grouped listing of imported plugins
  (extra_params.plugin_name → server names + has_bundled_files).
- uninstall_plugin: full plugin teardown — remove its MCP entries, unbind
  agent mcp_ids, and delete bundled/data directories; unsafe names are refused.
- _load_existing_skill_ids: active skill name → skill_id map (conflict SSOT).
- Re-exports PluginImportSession / PluginConfirmItem / PluginStaging /
  PluginArchiveSecurityError for the API layer and callers.

[POS]
Business-layer import orchestration for the open-source product: maps framework
parsing results into product persistence (SkillStore, global mcpServers,
Agent profile binding) with blue-green writes and disabled-by-default MCP.
"""

from __future__ import annotations

import logging
import uuid
import zipfile

from myrm_agent_harness.agent.plugins.models import (
    PluginParseResult,
)
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

from ._agent_persist import persist_imported_agents
from ._mcp_persist import (
    _bind_agent,
    _collect_required_secret_keys,
    _collect_server_configs,
    _write_mcp_servers,
)
from ._models import PluginConfirmItem, PluginImportSession
from ._preview import (
    build_preview_result,
    load_existing_skill_ids,
    scan_skill_security,
    skill_content_too_large,
)
from ._staging import PluginStaging
from ._uninstall import list_installed_plugins, uninstall_plugin

MAX_SKILL_CONTENT_CHARS = SkillStore.MAX_SKILL_CONTENT_CHARS

# Internal aliases preserved for unit tests that patch import_service attributes directly
_load_existing_skill_ids = load_existing_skill_ids
_scan_skill_security = scan_skill_security
_skill_content_too_large = skill_content_too_large
_persist_agents = persist_imported_agents

logger = logging.getLogger(__name__)

__all__ = [
    "PluginArchiveSecurityError",
    "PluginConfirmItem",
    "PluginImportSession",
    "PluginStaging",
    "build_preview_result",
    "confirm_plugin_import",
    "list_installed_plugins",
    "parse_plugin_zip",
    "uninstall_plugin",
]


class PluginArchiveSecurityError(ValueError):
    """A plugin ZIP was blocked by the archive security policy.

    Carries the canonical ``error_code`` so the API layer can build a
    structured detail payload and the frontend can localize the message.
    """

    def __init__(self, message: str, error_code: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code


def parse_plugin_zip(zip_bytes: bytes) -> PluginParseResult:
    """Parse a plugin ZIP and raise a user-facing error for fatal archive issues."""
    from myrm_agent_harness.backends.skills.scanning.archive_security import (
        ArchiveSecurityError,
        classify_archive_security_issue,
        format_archive_security_user_message,
    )

    try:
        return AgentPluginParser().parse_zip(zip_bytes)
    except ArchiveSecurityError as exc:
        violation = classify_archive_security_issue(exc)
        message = (
            format_archive_security_user_message(violation)
            if violation is not None
            else str(exc)
        )
        error_code = violation.code.value if violation is not None else ""
        raise PluginArchiveSecurityError(message, error_code=error_code) from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from exc


def _plugin_name_of(session: PluginImportSession) -> str | None:
    meta = session.plugin_result.meta
    return meta.name if meta is not None else None


def _persist_plugin_files_if_needed(
    session: PluginImportSession,
    server_decisions: list[PluginConfirmItem],
    plugin_name: str | None,
) -> tuple[str | None, str | None]:
    """Persist bundled plugin files when any accepted server needs them.

    Returns ``(plugin_root, data_root)`` absolute paths, or ``(None, None)``
    when no accepted server references the plugin package (nothing to persist)
    or the plugin name is missing/unsafe.
    """
    if not plugin_name:
        return None, None

    from ._plugin_files import persist_plugin_files, server_needs_bundled_files

    accepted = [
        decision
        for decision in server_decisions
        if decision.resolution != "skip"
        and session.servers_by_key.get(decision.virtual_id) is not None
    ]
    if not any(
        server_needs_bundled_files(session.servers_by_key[d.virtual_id])
        for d in accepted
    ):
        return None, None

    from app.core.skills.store.evolution_store import get_evolution_skill_store_db_path

    data_dir = get_evolution_skill_store_db_path().parent
    persisted = persist_plugin_files(plugin_name, session.plugin_result.files, data_dir)
    if persisted is None:
        return None, None
    return persisted


async def confirm_plugin_import(
    session: PluginImportSession,
    *,
    skill_decisions: list[PluginConfirmItem],
    server_decisions: list[PluginConfirmItem],
    agent_decisions: list[PluginConfirmItem] | None = None,
    bind_agent_id: str | None = None,
) -> dict[str, object]:
    """Persist selected skills, MCP servers, agents, and template workspace files."""
    skill_records, skill_ids, skipped_skills = _collect_skill_records(
        session, skill_decisions, _load_existing_skill_ids()
    )
    plugin_name = _plugin_name_of(session)
    plugin_root, data_root = _persist_plugin_files_if_needed(
        session, server_decisions, plugin_name
    )
    server_configs, skipped_servers = _collect_server_configs(
        session,
        server_decisions,
        plugin_name=plugin_name,
        plugin_root=plugin_root,
        data_root=data_root,
    )

    if skill_records:
        await _write_skills(skill_records)
    imported_server_names: list[str] = []
    required_secret_keys: list[str] = []
    if server_configs:
        imported_server_names = await _write_mcp_servers(server_configs)
        persisted_names = set(imported_server_names)
        required_secret_keys = _collect_required_secret_keys(
            [
                cfg
                for cfg in server_configs
                if str(cfg.get("name", "")) in persisted_names
            ]
        )

    # Persist imported Agents if provided in session/decisions
    imported_agent_ids, skipped_agents = await _persist_agents(
        session,
        agent_decisions or [],
        skill_ids=skill_ids,
        mcp_names=imported_server_names,
    )

    if bind_agent_id and (skill_ids or imported_server_names):
        await _bind_agent(
            skill_ids=skill_ids,
            server_names=imported_server_names,
            agent_id=bind_agent_id,
        )

    return {
        "imported_skills": len(skill_records),
        "skipped_skills": skipped_skills,
        "imported_servers": len(imported_server_names),
        "skipped_servers": skipped_servers,
        "imported_agents": len(imported_agent_ids),
        "skipped_agents": skipped_agents,
        "required_secret_keys": required_secret_keys,
        "created_agent_ids": imported_agent_ids,
    }


def _collect_skill_records(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    existing_ids: dict[str, str],
) -> tuple[list[SkillRecord], list[str], int]:
    plugin_name = (
        session.plugin_result.meta.name if session.plugin_result.meta else "plugin"
    )
    records: list[SkillRecord] = []
    skill_ids: list[str] = []
    skipped = 0
    for decision in decisions:
        if decision.resolution == "skip":
            skipped += 1
            continue
        skill = session.skills_by_key.get(decision.virtual_id)
        if skill is None:
            skipped += 1
            continue
        if _skill_content_too_large(skill):
            logger.warning(
                "Skipping oversized skill '%s' (%d chars, max %d)",
                skill.name,
                len(skill.content),
                MAX_SKILL_CONTENT_CHARS,
            )
            skipped += 1
            continue
        if _scan_skill_security(skill):
            skipped += 1
            continue

        existing_id = existing_ids.get(skill.name)
        if existing_id:
            # Same-name skill already installed: upgrade it in place so the
            # library never accumulates duplicate names. The authoritative map
            # is queried at confirm time (not the frontend's decision payload),
            # so any install/replace decision on a conflict resolves to overwrite.
            skill_id = existing_id
            lineage = SkillLineage(
                evolution_type=EvolutionType.DERIVED,
                version=1,
                parent_id=existing_id,
                change_summary=f"Upgraded via Agent Plugin '{plugin_name}'",
                created_by="plugin_import",
            )
        else:
            skill_id = str(uuid.uuid4())
            lineage = SkillLineage(
                evolution_type=EvolutionType.FIX,
                version=1,
                parent_id=None,
                change_summary=f"Imported via Agent Plugin '{plugin_name}'",
                created_by="plugin_import",
            )
        records.append(
            SkillRecord(
                skill_id=skill_id,
                name=skill.name,
                description=skill.description,
                content=skill.content,
                path=f"plugins/{plugin_name}/{skill.name}/SKILL.md",
                lineage=lineage,
            )
        )
        skill_ids.append(skill_id)
    return records, skill_ids, skipped


async def _write_skills(records: list[SkillRecord]) -> None:
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    store = get_evolution_skill_store()
    await store.save_skills_batch(records)

