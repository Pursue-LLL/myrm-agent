"""SSH Host Asset Management HTTP endpoints for remote access.

[INPUT]
- .schemas::SSHHostCreateRequest, SSHHostImportRequest
- app.remote_access.host_depot::HostAssetDepot
- myrm_agent_harness.toolkits.ssh_remote.models::SSHAuthType
- fastapi::APIRouter, HTTPException

[OUTPUT]
- hosts_router: Sub-router mounted on /api/v1/remote-access.

[POS]
Sub-router in app/api/remote_access/hosts_router.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.remote_access.schemas import (
    SSHHostCreateRequest,
    SSHHostImportRequest,
)
from app.core.utils.response_utils import success_response

logger = logging.getLogger(__name__)

hosts_router = APIRouter()


@hosts_router.get("/hosts")
async def list_ssh_hosts() -> dict[str, object]:
    """List encrypted SSH host records."""
    from app.remote_access.host_depot import HostAssetDepot

    depot = HostAssetDepot()
    hosts = depot.list_hosts()
    return success_response(
        data=[
            {
                "host_id": h.host_id,
                "hostname": h.hostname,
                "port": h.port,
                "username": h.username,
                "auth_type": h.auth_type,
                "tags": h.tags,
                "description": h.description,
            }
            for h in hosts
        ]
    )


@hosts_router.post("/hosts")
async def create_or_update_ssh_host(body: SSHHostCreateRequest) -> dict[str, object]:
    """Save an SSH host record with encrypted credentials."""
    from myrm_agent_harness.toolkits.ssh_remote.models import SSHAuthType

    from app.remote_access.host_depot import HostAssetDepot

    depot = HostAssetDepot()
    auth_enum = SSHAuthType(body.auth_type)
    rec = depot.save_host(
        host_id=body.host_id,
        hostname=body.hostname,
        port=body.port,
        username=body.username,
        auth_type=auth_enum,
        secret=body.secret,
        passphrase=body.passphrase,
        proxy_jump=body.proxy_jump,
        tags=body.tags,
        description=body.description,
    )
    return success_response(
        data={
            "host_id": rec.host_id,
            "hostname": rec.hostname,
            "port": rec.port,
            "username": rec.username,
            "auth_type": rec.auth_type,
            "tags": rec.tags,
            "description": rec.description,
        }
    )


@hosts_router.delete("/hosts/{host_id}")
async def delete_ssh_host(host_id: str) -> dict[str, object]:
    """Remove an SSH host record."""
    from app.remote_access.host_depot import HostAssetDepot

    depot = HostAssetDepot()
    ok = depot.delete_host(host_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Host not found")
    return success_response(data={"deleted": True, "host_id": host_id})


@hosts_router.post("/hosts/import-config")
async def import_ssh_config(body: SSHHostImportRequest) -> dict[str, object]:
    """Import SSH host configurations from config text."""
    from app.remote_access.host_depot import HostAssetDepot

    depot = HostAssetDepot()
    imported = depot.import_from_ssh_config(body.config_text)
    return success_response(
        data=[
            {
                "host_id": h.host_id,
                "hostname": h.hostname,
                "port": h.port,
                "username": h.username,
                "auth_type": h.auth_type,
                "tags": h.tags,
                "description": h.description,
            }
            for h in imported
        ]
    )


__all__ = ["hosts_router"]
