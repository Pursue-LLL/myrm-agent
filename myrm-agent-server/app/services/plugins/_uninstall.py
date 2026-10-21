"""Plugin uninstallation and installed-plugins listing (business layer).

Handles full 4-dimensional capability eviction when uninstalling plugins:
1. MCP servers and Agent binding revocation.
2. Tool registry memory metadata eviction.
3. Cron jobs cascade cleanup (managed jobs deleted, workflows auto-paused).
4. Physical bundle and data directory removal.

[INPUT]
- app.services.config.service::config_service (POS: persisted MCP server records.)
- app.core.skills.store.evolution_store (POS: skills database path.)
- ._mcp_persist (POS: MCP config queries and agent unbinding.)
- ._plugin_files (POS: safe plugin name check and directory removal.)

[OUTPUT]
- list_installed_plugins: query and group installed plugins by provenance.
- uninstall_plugin: perform 4-dimensional capability eviction for a plugin.

[POS]
Clean teardown module for Agent Plugins, maintaining lifecycle separation
from the installation orchestration pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "list_installed_plugins",
    "uninstall_plugin",
]


async def list_installed_plugins() -> list[dict[str, object]]:
    """Return imported plugins grouped by their provenance ``extra_params.plugin_name``.

    Only servers that were imported through this service carry the
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
                "capabilities": cfg.get("capabilities", []),
            }
        )

    result_list: list[dict[str, object]] = []
    for plugin_name, server_infos in sorted(by_plugin.items()):
        all_caps: set[str] = set()
        for item in server_infos:
            caps = item.get("capabilities")
            if isinstance(caps, list):
                all_caps.update(str(c) for c in caps)
        result_list.append(
            {
                "name": plugin_name,
                "servers": sorted(str(item["name"]) for item in server_infos),
                "server_meta": sorted(
                    server_infos,
                    key=lambda item: str(item["name"]),
                ),
                "has_bundled_files": _plugin_dir_exists(plugin_name),
                "capabilities": sorted(all_caps),
            }
        )
    return result_list


def _plugin_dir_exists(plugin_name: str) -> bool:
    """True when the plugin's bundled-file directory exists on disk."""
    try:
        from app.core.skills.store.evolution_store import (
            get_evolution_skill_store_db_path,
        )

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
        from myrm_agent_harness.api import evict_skill_safety_metadata

        evicted_tools += evict_skill_safety_metadata(plugin_name)
        for sname in server_names:
            evicted_tools += evict_skill_safety_metadata(sname)
    except Exception as exc:
        logger.warning("Failed to evict tool registry metadata for '%s': %s", plugin_name, exc)

    # D3: Associated Cron jobs cascade cleanup (dual-track)
    purged_cron_jobs = 0
    paused_cron_jobs = 0
    try:
        from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobStatus

        from app.core.cron.adapters.setup import get_cron_manager

        mgr = get_cron_manager()
        all_jobs = await mgr.list_jobs("default", limit=200)
        target_names = {plugin_name.lower(), *[s.lower() for s in server_names]}

        for job in all_jobs:
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
        from app.core.skills.store.evolution_store import (
            get_evolution_skill_store_db_path,
        )

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
