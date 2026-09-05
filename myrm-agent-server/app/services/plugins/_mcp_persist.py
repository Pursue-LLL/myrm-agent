"""MCP server persistence and agent binding for plugin imports.

Persists selected plugin MCP servers into the global ``mcpServers`` UserConfig
(disabled by default, merged with existing entries) and appends imported
skill ids / server names to an Agent profile.

[INPUT]
- ._models::PluginImportSession, PluginConfirmItem (POS: business-layer DTOs.)
- myrm_agent_harness.agent.plugins.models::PluginMcpServer (POS: framework
  parser output dataclasses.)
- app.services.config.service::config_service (POS: global UserConfig store.)
- app.core.channel_bridge.config_cache::invalidate_user_configs_cache (POS:
  force config cache invalidation after updates.)
- app.database.repositories.uow::UnitOfWork (POS: transactional agent profile
  repository access for bind/unbind.)

[OUTPUT]
- _collect_server_configs / _write_mcp_servers: MCP decision filtering + merge
  into mcpServers UserConfig; returns persisted names only.
- _server_to_config_dict: serialize a plugin MCP server (secret references +
  required_secrets for Scoped Secret Injection); embeds plugin_name / cwd / env
  and the persisted plugin_root / data_root into extra_params.
- _collect_required_secret_keys: dedupe secret keys an import requires.
- _bind_agent: atomically append skill_ids + mcp_ids to an Agent profile.
- _remove_plugin_mcp_servers: drop every mcpServers entry imported by a plugin
  name (uninstall).
- _unbind_plugin_from_agents: remove uninstalled server names from every
  agent's mcp_ids (uninstall).

[POS]
Business-layer MCP/agent persistence for plugin import (dedup by name,
disabled-by-default, atomic binding).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.plugins.models import PluginMcpServer

from ._models import PluginConfirmItem, PluginImportSession

if TYPE_CHECKING:
    from app.services.config.service import ConfigService

logger = logging.getLogger(__name__)

_SECRET_REF_PATTERN = re.compile(r"\{\{secret:([^}]+)\}\}")


def _collect_server_configs(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    *,
    plugin_name: str | None = None,
    plugin_root: str | None = None,
    data_root: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    configs: list[dict[str, object]] = []
    skipped = 0
    for decision in decisions:
        if decision.resolution == "skip":
            skipped += 1
            continue
        server = session.servers_by_key.get(decision.virtual_id)
        if server is None:
            skipped += 1
            continue
        if getattr(server, "missing_artifact", None) or not getattr(server, "is_runnable", True):
            logger.warning(
                "Skipping MCP server '%s' due to missing build artifact: %s",
                server.name,
                getattr(server, "missing_artifact", None) or "missing entrypoint",
            )
            skipped += 1
            continue
        configs.append(
            _server_to_config_dict(
                server,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                data_root=data_root,
            )
        )
    return configs, skipped


def _server_to_config_dict(
    server: PluginMcpServer,
    *,
    plugin_name: str | None = None,
    plugin_root: str | None = None,
    data_root: str | None = None,
) -> dict[str, object]:
    """Serialize a plugin MCP server into the mcpServers entry shape.

    ``plugin_name`` is always embedded (under ``extra_params``) as the uninstall
    provenance marker — the uninstall endpoint locates every entry imported by a
    plugin through it. ``plugin_root`` / ``data_root`` are only embedded when the
    server references the plugin package (a ``./`` command or a
    PLUGIN_ROOT/PLUGIN_DATA placeholder); remote servers and plain stdio
    commands get no plugin roots.
    """
    cfg: dict[str, object] = {
        "name": server.name,
        "type": server.server_type,
        "description": "Imported via Agent Plugin",
        "enabled": False,
        "connectTimeout": 15.0,
        "executeTimeout": 120.0,
        "hostSerial": False,
    }
    if server.command:
        cfg["command"] = server.command
    if server.args:
        cfg["args"] = server.args
    if server.url:
        cfg["url"] = server.url
    if server.headers:
        # Credential material never lands as plaintext: values that are already
        # secret references stay verbatim, anything else maps to a
        # ``{{secret:KEY}}`` reference keyed by the header name.
        cfg["headers"] = {k: (v if _is_secret_reference(v) else "{{secret:" + k + "}}") for k, v in server.headers.items()}
    extra_params: dict[str, object] = {}
    if plugin_name:
        extra_params["plugin_name"] = plugin_name
    if server.cwd:
        extra_params["cwd"] = server.cwd
    if server.raw_env:
        extra_params["env"] = server.raw_env
    if plugin_root and data_root:
        extra_params["plugin_root"] = plugin_root
        extra_params["data_root"] = data_root
    if extra_params:
        cfg["extra_params"] = extra_params
    if server.env_key_names:
        # Scoped Secret Injection: the runtime pulls only these keys from the
        # agent vault (mcp_runtime_prepare), never the full environment.
        cfg["required_secrets"] = list(server.env_key_names)
    return cfg


def _is_secret_reference(value: str) -> bool:
    return _SECRET_REF_PATTERN.search(value) is not None


def _collect_required_secret_keys(configs: list[dict[str, object]]) -> list[str]:
    """Collect secret keys a set of MCP entries depends on (env + header refs).

    Keys are deduplicated while preserving declaration order so the UI can guide
    the user to configure exactly the secrets a plugin import requires.
    """
    keys: list[str] = []
    for cfg in configs:
        required = cfg.get("required_secrets")
        if isinstance(required, list):
            keys.extend(str(key) for key in required if isinstance(key, str) and key.strip())
        headers = cfg.get("headers")
        if isinstance(headers, dict):
            for value in headers.values():
                if isinstance(value, str):
                    keys.extend(_SECRET_REF_PATTERN.findall(value))
    return list(dict.fromkeys(key.strip() for key in keys if key.strip()))


async def _write_mcp_servers(
    configs: list[dict[str, object]],
) -> list[str]:
    """Persist MCP servers, skipping existing names; returns persisted names.

    ``mcpServers`` is stored as ``{"mcpConfigs": [...]}`` to match the frontend
    config sync and runtime config loader contract. Existing user-configured
    servers are merged and preserved so a plugin import never drops them.
    The returned names reflect only entries actually written (a duplicate name
    is skipped, not counted, not bound).
    """
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.services.config.service import config_service

    existing = await _load_persisted_mcp_configs(config_service)

    existing_names = {str(cfg.get("name", "")) for cfg in existing if isinstance(cfg, dict)}
    new_configs: list[dict[str, object]] = []
    persisted_names: list[str] = []
    for cfg in configs:
        name = str(cfg.get("name", "")).strip()
        if not name or name in existing_names:
            continue
        entry = {**cfg, "enabled": False}
        existing.append(entry)
        existing_names.add(name)
        new_configs.append(entry)
        persisted_names.append(name)

    if new_configs:
        await config_service.set("mcpServers", {"mcpConfigs": existing}, device_id="plugin-import")
        invalidate_user_configs_cache()
    return persisted_names


async def _load_persisted_mcp_configs(
    config_service: "ConfigService",
) -> list[dict[str, object]]:
    """Load persisted MCP entries from the ``mcpServers`` UserConfig.

    Supports both the canonical ``{"mcpConfigs": [...]}`` envelope and a
    bare list payload. Returns an empty list when the record is absent or
    unreadable (corrupt payloads are replaced on save).
    """
    try:
        record = await config_service.get("mcpServers")
    except Exception as exc:
        logger.warning("Failed to load existing mcpServers config: %s", exc)
        return []
    if record is None:
        return []
    value = record.value
    if isinstance(value, dict):
        raw = value.get("mcpConfigs")
        return [cfg for cfg in raw if isinstance(cfg, dict)] if isinstance(raw, list) else []
    if isinstance(value, list):
        return [cfg for cfg in value if isinstance(cfg, dict)]
    return []


async def _bind_agent(
    agent_id: str,
    *,
    skill_ids: list[str],
    server_names: list[str],
) -> None:
    """Append imported skills + MCP server names to the agent profile.

    Uses a single ``AgentUpdate`` so skill and MCP bindings land atomically.
    Missing agents and duplicate ids are silently tolerated.
    """
    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    profile = await AgentService.get_agent_by_id(agent_id)
    if profile is None:
        return
    metadata = profile.metadata or {}
    update_fields: dict[str, list[str]] = {}
    if skill_ids:
        existing_skills = metadata.get("skill_ids", [])
        update_fields["skill_ids"] = list(dict.fromkeys([*(str(s) for s in existing_skills if isinstance(s, str)), *skill_ids]))
    if server_names:
        existing_servers = metadata.get("mcp_ids", [])
        update_fields["mcp_ids"] = list(
            dict.fromkeys(
                [
                    *(str(s) for s in existing_servers if isinstance(s, str)),
                    *server_names,
                ]
            )
        )
    if update_fields:
        await AgentService.update_agent(agent_id, AgentUpdate(**update_fields))


def _plugin_name_of_cfg(cfg: dict[str, object]) -> str | None:
    """Extract the provenance plugin name from an mcpServers entry (if any)."""
    extra = cfg.get("extra_params")
    if not isinstance(extra, dict):
        return None
    name = extra.get("plugin_name")
    return str(name) if isinstance(name, str) and name else None


async def _remove_plugin_mcp_servers(plugin_name: str) -> int:
    """Remove every mcpServers entry imported by ``plugin_name``.

    Returns the number of removed entries. The global mcpServers UserConfig is
    rewritten without the plugin's entries; user-configured servers are kept.
    """
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.services.config.service import config_service

    existing = await _load_persisted_mcp_configs(config_service)
    remaining: list[dict[str, object]] = []
    removed = 0
    for cfg in existing:
        if _plugin_name_of_cfg(cfg) == plugin_name:
            removed += 1
            continue
        remaining.append(cfg)

    if removed:
        await config_service.set("mcpServers", {"mcpConfigs": remaining}, device_id="plugin-uninstall")
        invalidate_user_configs_cache()
    return removed


async def _unbind_plugin_from_agents(server_names: list[str]) -> int:
    """Drop uninstalled server names from every agent's ``mcp_ids``.

    Returns the number of agent profiles updated. Missing agents and names that
    are not bound are silently tolerated.
    """
    from app.database.repositories.uow import UnitOfWork

    if not server_names:
        return 0
    targets = set(server_names)
    updated = 0
    async with UnitOfWork() as uow:
        profiles = await uow.agent_repo.list_profiles(limit=1000)
        for profile in profiles:
            metadata = profile.metadata or {}
            existing_servers = metadata.get("mcp_ids", [])
            kept = [str(s) for s in existing_servers if isinstance(s, str) and s not in targets]
            if len(kept) != len(existing_servers):
                await uow.agent_repo.update_profile(profile.id, {"metadata": {**metadata, "mcp_ids": kept}})
                updated += 1
    return updated
