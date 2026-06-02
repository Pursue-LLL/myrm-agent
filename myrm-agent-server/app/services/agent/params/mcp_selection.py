"""Per-agent MCP server and tool-level filtering.

[INPUT]
- app.core.types.business::MCPServerConfig (POS: MCP server configuration model)

[OUTPUT]
- apply_agent_mcp_selection(): filter MCP configs by agent's mcp_ids and inject tool_include from mcp_tool_selections
- coerce_tool_selections(): normalize raw mcp_tool_selections metadata into {server: (tool, ...)}

[POS]
Centralised MCP config filtering for agent execution paths. Ensures all five
entry points (Web, Channel, Voice, Eval, Subagent) consistently apply the
per-agent server-level (mcp_ids) and tool-level (mcp_tool_selections) constraints
stored in the agent profile.
"""

from __future__ import annotations

import logging

from app.core.types import MCPServerConfig

logger = logging.getLogger(__name__)


def coerce_tool_selections(val: object) -> dict[str, tuple[str, ...]] | None:
    """Normalize raw ``mcp_tool_selections`` into {server: (tool, ...)}.

    Tolerant of malformed data: non-dict input yields None; each
    server's value is coerced to a tuple of tool-name strings.
    Returns None instead of empty dict so callers can short-circuit.
    """
    if not isinstance(val, dict):
        return None
    out: dict[str, tuple[str, ...]] = {}
    for server, tools in val.items():
        if isinstance(tools, (list, tuple)):
            coerced = tuple(t for t in tools if isinstance(t, str))
        elif isinstance(tools, str):
            coerced = (tools,)
        else:
            continue
        if coerced:
            out[str(server)] = coerced
    return out or None


def apply_agent_mcp_selection(
    mcp_configs: list[MCPServerConfig],
    mcp_ids: tuple[str, ...] | None,
    mcp_tool_selections: dict[str, tuple[str, ...]] | None,
) -> list[MCPServerConfig]:
    """Filter *mcp_configs* by agent profile constraints.

    1. If *mcp_ids* is non-empty, only servers whose ``name`` is in *mcp_ids*
       are retained (server-level filtering).
    2. If *mcp_tool_selections* maps a retained server to a non-empty tool
       tuple, ``tool_include`` is set on a shallow copy of that config
       (tool-level filtering via ``model_copy``).

    Returns a **new** list; the original configs are never mutated.
    """
    if not mcp_configs:
        return []

    original_count = len(mcp_configs)
    configs = mcp_configs

    if mcp_ids:
        id_set = set(mcp_ids)
        configs = [c for c in configs if c.name in id_set]

    if not mcp_tool_selections:
        if len(configs) != original_count:
            logger.debug("MCP selection: %d servers -> %d (server-level only)", original_count, len(configs))
        return configs

    tool_injected = 0
    result: list[MCPServerConfig] = []
    for cfg in configs:
        tools = mcp_tool_selections.get(cfg.name)
        if tools:
            result.append(cfg.model_copy(update={"tool_include": list(tools)}))
            tool_injected += 1
        else:
            result.append(cfg)

    if len(result) != original_count or tool_injected:
        logger.debug(
            "MCP selection: %d servers -> %d, tool_include injected for %d",
            original_count, len(result), tool_injected,
        )
    return result
