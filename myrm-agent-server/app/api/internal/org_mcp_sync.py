"""Control Plane → sandbox Org MCP sync endpoint.

[INPUT]
- CP pushes org-level MCP server configurations via this internal API

[OUTPUT]
- POST /api/admin/org-mcp-sync: Stores org MCP configs in UserConfig table

[POS]
Receives organization-level MCP server configurations from Control Plane
and persists them locally under the 'orgMcpServers' config key.
On next agent execution, config_loader merges org MCPs with user MCPs.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.services.config.service import ConfigService

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"
_ORG_MCP_CONFIG_KEY = "orgMcpServers"


class OrgMCPSyncRequest(BaseModel):
    mcp_servers: list[dict]


class OrgMCPSyncResponse(BaseModel):
    status: str = "synced"
    count: int = 0


def _verify_cp_token(request: Request) -> None:
    """Verify the request comes from the Control Plane."""
    expected = os.environ.get(_CP_TOKEN_ENV)
    if not expected:
        return
    token = request.headers.get(_CP_TOKEN_HEADER, "")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid CP token")


@router.post("/api/admin/org-mcp-sync", response_model=OrgMCPSyncResponse)
async def org_mcp_sync(request: Request, body: OrgMCPSyncRequest) -> OrgMCPSyncResponse:
    """Receive org-level MCP servers from Control Plane and persist locally."""
    _verify_cp_token(request)

    config_svc = ConfigService()
    servers_data = {"servers": body.mcp_servers}

    await config_svc.set(
        config_key=_ORG_MCP_CONFIG_KEY,
        value=servers_data,
        device_id="control_plane",
    )

    invalidate_user_configs_cache()

    logger.info("Org MCP sync: received %d servers", len(body.mcp_servers))
    return OrgMCPSyncResponse(status="synced", count=len(body.mcp_servers))
