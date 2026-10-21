"""Agent Plugins 1.0.0 import orchestration (business layer).

Consumes the framework-level parser (`myrm_agent_harness.agent.plugins`) and
persists the selected components:
  - skills → installed like any external skill (quarantine pipeline, lifecycle +
    security gates over every file, atomic promote) and enabled in the catalog
  - MCP servers → global ``mcpServers`` UserConfig (disabled by default)
  - experts → ``AgentService`` (per-expert bindings, tighten-only fields, same-name
    policies, rollback on failure)
  - optional binding of the imported skills/servers to an existing expert

The import is fully offline (no LLM calls) and applies per-component failure
isolation: a rejected skill, a blocked connector or an invalid expert is reported
in ``failures`` and never aborts the rest, and nothing half-written is left behind.

[INPUT]
- myrm_agent_harness.agent.plugins.parser::AgentPluginParser (POS: framework
  plugin archive parser.)
- ._skill_persist::install_plugin_skills (POS: skill installation + catalog enable.)
- ._agent_persist::persist_imported_agents (POS: expert persistence.)
- ._preview_context::load_preview_context (POS: installation state at confirm time.)
- ._mcp_persist (POS: MCP/agent persistence for plugin imports.)
- ._models::PluginImportSession, PluginConfirmItem (POS: business-layer DTOs.)
- ._staging::PluginStaging (POS: import session staging persistence.)

[OUTPUT]
- build_preview_result: component preview payload with conflict / block / unresolved flags.
- load_preview_context: installation state a package is previewed and confirmed against.
- confirm_plugin_import: persist skills, MCP servers and experts from a parsed plugin
  archive; returns imported/skipped counts, per-component ``failures``, per-expert
  results and ``required_secret_keys`` for the UI to guide secret configuration.
  Bundled plugin files are persisted via ``._plugin_files.persist_plugin_files`` and
  their roots embedded into ``extra_params`` (plugin_root / data_root).
- list_installed_plugins: provenance-grouped listing of imported plugins
  (extra_params.plugin_name → server names + has_bundled_files).
- uninstall_plugin: full plugin teardown — remove its MCP entries, unbind
  agent mcp_ids, and delete bundled/data directories; unsafe names are refused.
- Re-exports PluginImportSession / PluginConfirmItem / PluginStaging /
  PluginArchiveSecurityError for the API layer and callers.

[POS]
Business-layer import orchestration for the open-source product: maps framework
parsing results into product persistence (installed skills, global mcpServers,
expert profiles) with disabled-by-default MCP.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import asdict

from myrm_agent_harness.agent.plugins.models import PluginParseResult
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser

from ._agent_persist import AgentImportEntry, persist_imported_agents
from ._mcp_persist import (
    _bind_agent,
    _collect_required_secret_keys,
    _collect_server_configs,
    _write_mcp_servers,
)
from ._models import ComponentFailure, PluginConfirmItem, PluginImportSession
from ._preview import build_preview_result
from ._preview_context import load_preview_context
from ._skill_persist import install_plugin_skills
from ._staging import PluginStaging
from ._uninstall import list_installed_plugins, uninstall_plugin

logger = logging.getLogger(__name__)

__all__ = [
    "PluginArchiveSecurityError",
    "PluginConfirmItem",
    "PluginImportSession",
    "PluginStaging",
    "build_preview_result",
    "confirm_plugin_import",
    "list_installed_plugins",
    "load_preview_context",
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
        message = format_archive_security_user_message(violation) if violation is not None else str(exc)
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
        if decision.resolution != "skip" and session.servers_by_key.get(decision.virtual_id) is not None
    ]
    if not any(server_needs_bundled_files(session.servers_by_key[d.virtual_id]) for d in accepted):
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
    """Persist the selected skills, MCP servers and experts of a previewed package."""
    plugin_name = _plugin_name_of(session)
    # Facts are re-read here: preview flags are UI hints only, never trusted.
    context = await load_preview_context([agent.name for agent in session.agents_by_key.values()])

    skills = await install_plugin_skills(
        session,
        skill_decisions,
        plugin_name=plugin_name or "plugin",
        allows_local_skills=context.allows_local_skills,
    )

    plugin_root, data_root = _persist_plugin_files_if_needed(session, server_decisions, plugin_name)
    server_configs, skipped_servers, server_failures = _collect_server_configs(
        session,
        server_decisions,
        allow_stdio=context.allow_stdio,
        plugin_name=plugin_name,
        plugin_root=plugin_root,
        data_root=data_root,
    )
    imported_server_names: list[str] = []
    required_secret_keys: list[str] = []
    if server_configs:
        imported_server_names = await _write_mcp_servers(server_configs)
        persisted_names = set(imported_server_names)
        required_secret_keys = _collect_required_secret_keys(
            [cfg for cfg in server_configs if str(cfg.get("name", "")) in persisted_names]
        )

    agents = await persist_imported_agents(
        session,
        agent_decisions or [],
        context=context,
        imported_skill_ids=skills.installed_ids,
        imported_servers=imported_server_names,
    )

    if bind_agent_id and (skills.installed_ids or imported_server_names):
        await _bind_agent(
            bind_agent_id,
            skill_ids=list(skills.installed_ids.values()),
            server_names=imported_server_names,
        )

    failures: list[ComponentFailure] = [*skills.failures, *server_failures, *agents.failures]
    return {
        "imported_skills": len(skills.installed_ids),
        "skipped_skills": skills.skipped,
        "imported_servers": len(imported_server_names),
        "skipped_servers": skipped_servers,
        "imported_agents": len(agents.entries),
        "skipped_agents": agents.skipped,
        "required_secret_keys": required_secret_keys,
        "created_agent_ids": agents.agent_ids,
        "agents": [_agent_result(entry) for entry in agents.entries],
        "failures": [asdict(failure) for failure in failures],
    }


def _agent_result(entry: AgentImportEntry) -> dict[str, object]:
    return {
        "agent_id": entry.agent_id,
        "package_name": entry.package_name,
        "stored_name": entry.stored_name,
        "action": entry.action,
        "previous_version_saved": entry.previous_version_saved,
        "withheld_tools": list(entry.withheld_tools),
        "unresolved_skills": list(entry.unresolved_skills),
        "unresolved_connectors": list(entry.unresolved_connectors),
        "unresolved_subagents": list(entry.unresolved_subagents),
    }
