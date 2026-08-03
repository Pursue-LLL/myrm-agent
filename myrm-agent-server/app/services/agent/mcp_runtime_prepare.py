"""Prepare MCP server configs for harness runtime routing (secrets + OAuth).

[INPUT]
- app.services.agent.backends::DatabaseSecretBackend, MCPSecretAuthProvider (POS: agent secret store)
- app.ai_agents.general_agent.factory::_try_inject_mcp_oauth (POS: MCP OAuth header injection)

[OUTPUT]
- prepare_mcp_configs_for_runtime(): MCP configs enriched for route_mcp_servers / hot reload

[POS]
Server business layer. Shared by GeneralAgent factory build and catalog capability hot reload.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.mcp.config import MCPConfig

logger = logging.getLogger(__name__)


async def prepare_mcp_configs_for_runtime(
    agent_id: str | None,
    configs: list[MCPConfig],
) -> list[MCPConfig]:
    """Inject agent secrets and OAuth providers into MCP configs before routing."""
    if not agent_id or not configs:
        return list(configs)

    try:
        from app.core.security import MasterKeyProvider
        from app.services.agent.backends import (
            DatabaseSecretBackend,
            MCPSecretAuthProvider,
        )

        master_key = MasterKeyProvider.get_master_key()
        secret_store = DatabaseSecretBackend(master_key=master_key)
        global_env = await secret_store.get_all_secrets(agent_id)
        if global_env:
            logger.info("Loaded %d secrets for agent %s MCP runtime prepare", len(global_env), agent_id)

        prepared: list[MCPConfig] = []
        for cfg in configs:
            if cfg.type == "stdio":
                ep_raw = cfg.extra_params or {}
                extra_params: dict[str, object] = dict(ep_raw) if isinstance(ep_raw, dict) else {}
                env_raw = extra_params.get("env")
                env: dict[str, str] = {}
                if isinstance(env_raw, dict):
                    for key, value in env_raw.items():
                        if isinstance(key, str) and isinstance(value, str):
                            env[key] = value

                req_keys = getattr(cfg, "required_secrets", None)
                if req_keys and global_env:
                    for req_key in req_keys:
                        if req_key in global_env:
                            env[req_key] = global_env[req_key]
                        else:
                            logger.warning(
                                "MCP server '%s' requires secret '%s', but it is not found in agent secrets.",
                                cfg.name,
                                req_key,
                            )

                extra_params["env"] = env
                prepared.append(cfg.model_copy(update={"extra_params": extra_params}))
                continue

            cfg_headers = getattr(cfg, "headers", None) or {}
            has_secret_refs = (
                any("{{secret:" in value for value in cfg_headers.values()) if cfg_headers else False
            )
            if has_secret_refs:
                auth_provider = MCPSecretAuthProvider(
                    header_templates=cfg_headers,
                    secret_store=secret_store,
                    agent_id=agent_id,
                )
                prepared.append(cfg.model_copy(update={"auth_provider": auth_provider}))
                continue

            from app.ai_agents.general_agent.factory import _try_inject_mcp_oauth

            prepared.append(await _try_inject_mcp_oauth(cfg))

        return prepared
    except Exception as exc:
        logger.warning("Failed to prepare MCP configs for agent %s: %s", agent_id, exc)
        return list(configs)
