"""Control Plane → sandbox Org MCP sync endpoint.

[INPUT]
- CP pushes org-level MCP server configurations via this internal API

[OUTPUT]
- POST /api/admin/org-mcp-sync: Stores org MCP configs in UserConfig table

[POS]
Receives organization-level MCP server configurations from Control Plane
and persists them locally under the 'orgMcpServers' config key.
At agent execution time, `config_parsers.merge_org_mcp_configs` appends org
MCPs to the user MCP config across every execution entry point.
Servers pushed without `type` are normalized (command→stdio, url→sse) so
`MCPServerConfig` validation never silently drops them.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config.settings import settings
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.security.auth.control_plane_guard import verify_control_plane_token
from app.services.config.service import ConfigService

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_control_plane_token)])

_ORG_MCP_CONFIG_KEY = "orgMcpServers"


class OrgMCPSyncRequest(BaseModel):
    mcp_servers: list[dict]


class OrgMCPSyncResponse(BaseModel):
    status: str = "synced"
    count: int = 0


def _normalize_mcp_server_types(servers: list[dict]) -> list[dict]:
    """Infer the ``type`` field for org MCP servers pushed without one.

    Control Plane payloads may omit ``type``; without it
    ``extract_org_mcp_configs`` rejects the server via ``MCPServerConfig``
    validation and the org MCP silently disappears from every agent. Infer
    from the transport fields instead (command/args → stdio, url → sse).
    """
    normalized: list[dict] = []
    for server in servers:
        entry = dict(server)
        if not entry.get("type"):
            if entry.get("command"):
                entry["type"] = "stdio"
            elif entry.get("url"):
                entry["type"] = "sse"
        normalized.append(entry)
    return normalized


def _filter_mcp_servers_for_sandbox(servers: list[dict]) -> list[dict]:
    """Drop stdio org MCP entries when sandbox policy disables stdio."""
    if settings.mcp.allow_stdio:
        return servers
    allowed: list[dict] = []
    for server in servers:
        if server.get("type") == "stdio":
            logger.warning(
                "Org MCP sync skipped stdio server %s: stdio disabled in sandbox",
                server.get("name", server.get("id", "unknown")),
            )
            continue
        allowed.append(server)
    return allowed


@router.post("/api/admin/org-mcp-sync", response_model=OrgMCPSyncResponse)
async def org_mcp_sync(request: Request, body: OrgMCPSyncRequest) -> OrgMCPSyncResponse:
    """Receive org-level MCP servers from Control Plane and persist locally."""
    _verify_cp_token(request)

    normalized_servers = _normalize_mcp_server_types(body.mcp_servers)
    filtered_servers = _filter_mcp_servers_for_sandbox(normalized_servers)
    config_svc = ConfigService()
    servers_data = {"servers": filtered_servers}

    await config_svc.set(
        config_key=_ORG_MCP_CONFIG_KEY,
        value=servers_data,
        device_id="control_plane",
    )

    invalidate_user_configs_cache()

    logger.info("Org MCP sync: received %d servers", len(filtered_servers))
    return OrgMCPSyncResponse(status="synced", count=len(filtered_servers))
