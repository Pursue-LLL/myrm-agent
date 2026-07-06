"""Convert external MCP server configs into MCPServerConfig format.

[INPUT]
Raw mcp_servers dict from competitor payload (hermes config.yaml / claude settings.json / openclaw config.json).

[OUTPUT]
List of MCPMigrationItem — each carrying the converted MCPServerConfig and migration metadata.

[POS]
Stateless converter bridging migration loaders and the MCP configuration store.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPMigrationItem:
    """One MCP server detected from a competitor install, ready for preview and user approval."""

    name: str
    server_type: str
    command: str | None
    args: list[str] | None
    url: str | None
    description: str
    connect_timeout: float
    execute_timeout: float
    tool_include: list[str] | None
    tool_exclude: list[str] | None
    env_key_names: list[str]


def convert_competitor_mcp_servers(
    raw_servers: dict[str, object],
    *,
    competitor: str,
) -> list[MCPMigrationItem]:
    """Convert competitor mcp_servers dict into a list of MCPMigrationItem."""

    items: list[MCPMigrationItem] = []
    for name, raw in raw_servers.items():
        if not isinstance(raw, dict):
            continue
        item = _convert_one(name, raw, competitor=competitor)
        if item is not None:
            items.append(item)
    return items


def _convert_one(
    name: str,
    raw: dict[str, object],
    *,
    competitor: str,
) -> MCPMigrationItem | None:
    command = _str_or_none(raw, "command")
    url = _str_or_none(raw, "url")

    if command:
        server_type = "stdio"
    elif url:
        transport = _str_or_none(raw, "type") or _str_or_none(raw, "transport") or ""
        if transport.lower() in ("streamable_http", "streamable-http"):
            server_type = "streamable_http"
        else:
            server_type = "sse"
    else:
        return None

    args_raw = raw.get("args")
    args = [str(a) for a in args_raw] if isinstance(args_raw, list) else None

    env_key_names = _extract_env_key_names(raw)

    connect_timeout = _float_or_default(raw, "connectTimeout", "connect_timeout", default=15.0)
    execute_timeout = _float_or_default(raw, "timeout", "execute_timeout", default=120.0)

    tool_include, tool_exclude = _extract_tool_filters(raw)

    desc_parts: list[str] = []
    desc_raw = _str_or_none(raw, "description")
    if desc_raw:
        desc_parts.append(desc_raw)
    desc_parts.append(f"Migrated from {competitor}")
    description = " — ".join(desc_parts)

    return MCPMigrationItem(
        name=name,
        server_type=server_type,
        command=command,
        args=args,
        url=url,
        description=description,
        connect_timeout=connect_timeout,
        execute_timeout=execute_timeout,
        tool_include=tool_include,
        tool_exclude=tool_exclude,
        env_key_names=env_key_names,
    )


def mcp_migration_item_to_config_dict(item: MCPMigrationItem) -> dict[str, object]:
    """Serialize an MCPMigrationItem into a dict matching frontend MCPServiceConfig shape.

    The output is suitable for writing into the mcpServers UserConfig entry.
    All migrated configs default to ``enabled: false`` so the user must explicitly enable.
    """

    cfg: dict[str, object] = {
        "name": item.name,
        "type": item.server_type,
        "description": item.description,
        "enabled": False,
        "connectTimeout": item.connect_timeout,
        "executeTimeout": item.execute_timeout,
    }
    if item.command:
        cfg["command"] = item.command
    if item.args:
        cfg["args"] = item.args
    if item.url:
        cfg["url"] = item.url
    if item.tool_include:
        cfg["tool_include"] = item.tool_include
    if item.tool_exclude:
        cfg["tool_exclude"] = item.tool_exclude
    return cfg


def mcp_migration_item_to_preview(item: MCPMigrationItem) -> dict[str, object]:
    """Build a compact preview dict for the frontend migration wizard."""

    preview: dict[str, object] = {
        "name": item.name,
        "type": item.server_type,
    }
    if item.command:
        preview["command"] = item.command
        if item.args:
            preview["commandPreview"] = f"{item.command} {' '.join(item.args[:3])}"
    if item.url:
        preview["url"] = item.url
    if item.env_key_names:
        preview["envKeyCount"] = len(item.env_key_names)
    return preview


def _str_or_none(d: dict[str, object], key: str) -> str | None:
    v = d.get(key)
    return str(v).strip() if isinstance(v, str) and v else None


def _float_or_default(d: dict[str, object], *keys: str, default: float) -> float:
    for key in keys:
        v = d.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return default


def _extract_env_key_names(raw: dict[str, object]) -> list[str]:
    """Extract environment variable key names, stripping actual values for security."""

    env = raw.get("env")
    if isinstance(env, dict):
        return [str(k) for k in env if isinstance(k, str)]
    return []


def _extract_tool_filters(raw: dict[str, object]) -> tuple[list[str] | None, list[str] | None]:
    tools_cfg = raw.get("tools")
    if not isinstance(tools_cfg, dict):
        return None, None

    include_raw = tools_cfg.get("include")
    include = [str(t) for t in include_raw if isinstance(t, str)] if isinstance(include_raw, list) else None

    exclude_raw = tools_cfg.get("exclude")
    exclude = [str(t) for t in exclude_raw if isinstance(t, str)] if isinstance(exclude_raw, list) else None

    return include or None, exclude or None
