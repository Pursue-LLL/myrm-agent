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
    PluginMcpServer,
    PluginParseResult,
    PluginSkill,
)
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

from ._mcp_persist import (
    _bind_agent,
    _collect_required_secret_keys,
    _collect_server_configs,
    _write_mcp_servers,
)
from ._models import PluginConfirmItem, PluginImportSession
from ._staging import PluginStaging

MAX_SKILL_CONTENT_CHARS = SkillStore.MAX_SKILL_CONTENT_CHARS

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
        message = format_archive_security_user_message(violation) if violation is not None else str(exc)
        error_code = violation.code.value if violation is not None else ""
        raise PluginArchiveSecurityError(message, error_code=error_code) from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from exc


def _scan_skill_security(skill: PluginSkill) -> list[str]:
    """Scan a plugin skill for dangerous content (mirrors batch import).

    Returns a list of human-readable issues; an empty list means the skill passed.
    A scanner failure is treated as unsafe (fail-closed) so a broken validator
    never lets a skill install silently or aborts the whole import.
    """
    from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
    from myrm_agent_harness.agent.skills.optimization.security import (
        SkillSecurityValidator,
    )

    try:
        validator = SkillSecurityValidator(config=SecurityConfig())
        full_skill = f"---\nname: {skill.name}\ndescription: {skill.description}\n---\n{skill.content}"
        result = validator.validate_skill(full_skill)
    except Exception as exc:  # fail-closed: unable to verify -> blocked
        logger.warning("Skill security scan failed for %r: %s", skill.name, exc)
        return [f"Security scan failed: {exc}"]
    return result.issues if not result.passed else []


def _load_existing_skill_ids() -> dict[str, str]:
    """Map active skill names to their skill_ids (conflict-detection SSOT).

    Queried at preview and again at confirm time so the decision always reflects
    the latest store state (preview flags are UI hints only, never trusted).
    """
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    store = get_evolution_skill_store()
    return {skill.name: skill.skill_id for skill in store.get_active_skills()}


def build_preview_result(
    result: PluginParseResult,
    existing_names: set[str] | None = None,
) -> dict[str, object]:
    """Serialize a parse result into the preview response payload.

    ``existing_names`` marks skills that already exist in the store so the UI
    can offer replace/skip instead of silently duplicating them.
    """
    meta = result.meta
    existing = existing_names or set()
    return {
        "plugin": {
            "name": meta.name if meta else "",
            "version": meta.version if meta else None,
            "description": meta.description if meta else None,
            "author": meta.author if meta else None,
            "homepage": meta.homepage if meta else None,
            "repository": meta.repository if meta else None,
            "license": meta.license if meta else None,
            "keywords": list(meta.keywords) if meta else [],
        },
        "skills": [_preview_skill(idx, skill, existing) for idx, skill in enumerate(result.skills)],
        "servers": [
            {
                "name": server.name,
                "type": server.server_type,
                "command": server.command,
                "url": server.url,
                "env_key_count": len(server.env_key_names),
                "has_placeholders": _server_has_placeholders(server),
                "virtual_id": f"mcp:{idx}",
            }
            for idx, server in enumerate(result.servers)
        ],
        "diagnostics": [
            {
                "component": d.component,
                "code": d.code,
                "message": d.message,
                "level": d.level.value,
            }
            for d in result.diagnostics
        ],
        "is_valid": meta is not None,
    }


def _preview_skill(idx: int, skill: PluginSkill, existing_names: set[str]) -> dict[str, object]:
    """Serialize one skill for the preview payload."""
    oversized = _skill_content_too_large(skill)
    return {
        "name": skill.name,
        "description": skill.description,
        "file_count": len(skill.files),
        "virtual_id": f"skill:{idx}",
        # Oversized skills can never be installed; skip the security scan so the
        # preview mirrors confirm-time behavior instead of doing wasted work.
        "security_issues": [] if oversized else _scan_skill_security(skill),
        "oversized_content": oversized,
        "conflict": skill.name in existing_names,
    }


def _skill_content_too_large(skill: PluginSkill) -> bool:
    """True when the skill content exceeds the framework's storage limit."""
    return bool(skill.content) and len(skill.content) > MAX_SKILL_CONTENT_CHARS


def _server_has_placeholders(server: PluginMcpServer) -> bool:
    from myrm_agent_harness.agent.plugins.mcp_config import has_placeholders

    values: list[str | None] = [server.cwd]
    if server.args:
        values.extend(server.args)
    values.extend(server.raw_env.values())
    return has_placeholders(*values)


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
    bind_agent_id: str | None,
) -> dict[str, object]:
    """Persist selected skills + MCP servers and optionally bind them to an agent.

    Skills are installed with ``EvolutionType.FIX`` lineage when new, or upgraded
    in place with ``EvolutionType.DERIVED`` lineage when a same-name skill already
    exists. MCP servers are appended to the global ``mcpServers`` UserConfig
    disabled. When ``bind_agent_id`` is set, imported skill ids and server names
    are appended to the agent's ``skill_ids`` / ``mcp_ids``.

    Bundled MCP servers (``./`` commands or PLUGIN_ROOT/PLUGIN_DATA placeholders)
    have their plugin files persisted to ``{data_dir}/plugins/{plugin_name}/`` so
    the server can actually launch; the resulting ``plugin_root`` / ``data_root``
    are embedded into each entry's ``extra_params``.
    """
    skill_records, skill_ids, skipped_skills = _collect_skill_records(session, skill_decisions, _load_existing_skill_ids())
    plugin_name = _plugin_name_of(session)
    plugin_root, data_root = _persist_plugin_files_if_needed(session, server_decisions, plugin_name)
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
        # Only entries actually persisted (dedup skips existing names) drive the
        # secret guidance; a name-collision skip must not ask for new secrets.
        required_secret_keys = _collect_required_secret_keys(
            [cfg for cfg in server_configs if str(cfg.get("name", "")) in persisted_names]
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
        "required_secret_keys": required_secret_keys,
    }


def _collect_skill_records(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    existing_ids: dict[str, str],
) -> tuple[list[SkillRecord], list[str], int]:
    plugin_name = session.plugin_result.meta.name if session.plugin_result.meta else "plugin"
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


async def list_installed_plugins() -> list[dict[str, object]]:
    """List plugins with at least one imported MCP server entry.

    Groups global mcpServers entries by their provenance ``plugin_name`` marker
    (see ``_server_to_config_dict``) and reports the bound server names, plus
    each server's current ``enabled`` state, per plugin. Entries without a
    plugin marker (user-configured servers) are not listed here.
    """
    from app.services.config.service import config_service

    from ._mcp_persist import _load_persisted_mcp_configs

    entries = await _load_persisted_mcp_configs(config_service)
    by_plugin: dict[str, list[dict[str, object]]] = {}
    for cfg in entries:
        name = str(cfg.get("name", "")).strip()
        extra = cfg.get("extra_params")
        plugin_name = None
        if isinstance(extra, dict):
            raw = extra.get("plugin_name")
            if isinstance(raw, str) and raw:
                plugin_name = raw
        if not plugin_name or not name:
            continue
        by_plugin.setdefault(plugin_name, []).append(
            {
                "name": name,
                "enabled": False if cfg.get("enabled") is not True else True,
            }
        )

    return [
        {
            "name": plugin_name,
            "servers": sorted(str(item["name"]) for item in server_infos),
            "server_meta": sorted(
                server_infos,
                key=lambda item: str(item["name"]),
            ),
            "has_bundled_files": _plugin_dir_exists(plugin_name),
        }
        for plugin_name, server_infos in sorted(by_plugin.items())
    ]


def _plugin_dir_exists(plugin_name: str) -> bool:
    """True when the plugin's bundled-file directory exists on disk."""
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store_db_path

        from ._plugin_files import is_safe_plugin_name, plugin_dir_exists

        if not is_safe_plugin_name(plugin_name):
            return False
        data_dir = get_evolution_skill_store_db_path().parent
        return plugin_dir_exists(data_dir, plugin_name)
    except Exception as exc:  # defensive: listing must never fail on lookup
        logger.warning("Failed to check plugin dir for '%s': %s", plugin_name, exc)
        return False


async def uninstall_plugin(plugin_name: str) -> dict[str, object]:
    """Uninstall a plugin: remove its MCP servers, agent bindings, tools, cron jobs, and files.

    Performs complete 4-Dimensional Runtime Capability Eviction:
    1. MCP Server process/config teardown & Agent binding revocation
    2. Tool Registry memory eviction (O(1) thread-safe unregistration)
    3. Associated Cron jobs cascade cleanup (managed jobs deleted, workflows auto-paused)
    4. Physical bundle & data directory removal + audit log
    """
    from ._plugin_files import is_safe_plugin_name

    if not is_safe_plugin_name(plugin_name):
        logger.warning("Refusing to uninstall plugin with unsafe name %r", plugin_name)
        return {
            "plugin_name": plugin_name,
            "removed_servers": 0,
            "unbound_agents": 0,
            "evicted_tools": 0,
            "purged_cron_jobs": 0,
            "paused_cron_jobs": 0,
            "removed_files": False,
        }

    from ._mcp_persist import (
        _remove_plugin_mcp_servers,
        _unbind_plugin_from_agents,
    )

    installed = await list_installed_plugins()
    server_names: list[str] = []
    for item in installed:
        if item["name"] == plugin_name:
            server_names = [str(s) for s in item["servers"]]
            break

    # D1: MCP Servers removal and Agent unbinding
    removed_servers = await _remove_plugin_mcp_servers(plugin_name)
    unbound_agents = await _unbind_plugin_from_agents(server_names)

    # D2: Tool Registry memory eviction
    evicted_tools = 0
    try:
        from myrm_agent_harness.core.security.tool_registry.registry import (
            evict_skill_safety_metadata,
        )

        evicted_tools += evict_skill_safety_metadata(plugin_name)
        for sname in server_names:
            evicted_tools += evict_skill_safety_metadata(sname)
    except Exception as exc:
        logger.warning("Failed to evict tool registry metadata for '%s': %s", plugin_name, exc)

    # D3: Associated Cron jobs cascade cleanup (dual-track)
    purged_cron_jobs = 0
    paused_cron_jobs = 0
    try:
        from app.core.cron.adapters.setup import get_cron_manager
        from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobStatus

        mgr = get_cron_manager()
        all_jobs = await mgr.list_jobs("default", limit=200)
        target_names = {plugin_name.lower(), *[s.lower() for s in server_names]}

        for job in all_jobs:
            # Check if this job is managed directly by or references the plugin/servers
            job_name_lower = job.name.lower()
            job_prompt_lower = (job.prompt or "").lower()
            is_plugin_job = any(tn in job_name_lower for tn in target_names)
            is_referencing_job = any(tn in job_prompt_lower for tn in target_names)

            if is_plugin_job:
                deleted = await mgr.delete_job(job.id, "default")
                if deleted:
                    purged_cron_jobs += 1
            elif is_referencing_job and job.status == JobStatus.ACTIVE:
                await mgr.update_job(
                    job.id,
                    "default",
                    CronJobPatch(
                        status=JobStatus.PAUSED,
                    ),
                )
                paused_cron_jobs += 1
    except Exception as exc:
        logger.warning("Failed to cascade-clean cron jobs for '%s': %s", plugin_name, exc)

    # D4: Physical files removal
    removed_files = False
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store_db_path

        from ._plugin_files import remove_plugin_files

        data_dir = get_evolution_skill_store_db_path().parent
        removed_files = remove_plugin_files(plugin_name, data_dir)
    except Exception as exc:
        logger.warning("Failed to remove plugin files for '%s': %s", plugin_name, exc)

    logger.info(
        "Plugin %s evicted: %d servers, %d agents unbound, %d tools evicted, %d cron deleted, %d cron paused, files=%s",
        plugin_name,
        removed_servers,
        unbound_agents,
        evicted_tools,
        purged_cron_jobs,
        paused_cron_jobs,
        removed_files,
    )

    return {
        "plugin_name": plugin_name,
        "removed_servers": removed_servers,
        "unbound_agents": unbound_agents,
        "evicted_tools": evicted_tools,
        "purged_cron_jobs": purged_cron_jobs,
        "paused_cron_jobs": paused_cron_jobs,
        "removed_files": removed_files,
    }
