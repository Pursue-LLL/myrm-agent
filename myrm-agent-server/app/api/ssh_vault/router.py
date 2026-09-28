"""API routes for SSH Host Asset Management, Probing, and Security Gates.

[INPUT]
- fastapi::APIRouter, HTTPException, Query, Body
- pydantic::BaseModel, Field
- app.services.ssh_vault::SSHAssetService, SSHAssetSummary, SSHProbeResult, SSHCommandPayload, SSHCommandResult

[OUTPUT]
- router: FastAPI APIRouter instance
- BreakGlassRequest, BreakGlassResponse, HostPolicyUpdate

[POS]
API endpoints in app/api/ssh_vault/.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.ssh_vault.models import (
    SSHAssetSummary,
    SSHCommandPayload,
    SSHCommandResult,
    SSHProbeResult,
)
from app.services.ssh_vault.service import get_ssh_asset_service

logger = logging.getLogger("myrm.api.ssh_vault")

router = APIRouter(prefix="/ssh-vault", tags=["ssh-vault"])


class BreakGlassRequest(BaseModel):
    """Payload to request single-use break-glass authorization."""

    host_alias: str = Field(..., description="Target host alias")
    command: str = Field(..., description="Exact command requiring break-glass permission")
    reason: str = Field(..., min_length=3, description="Justification for emergency break-glass")
    ttl_seconds: int = Field(default=300, ge=30, le=1800, description="Token validity window in seconds")


class BreakGlassResponse(BaseModel):
    """Response containing single-use authorization token."""

    token: str = Field(..., description="One-time break-glass token")
    host_alias: str
    reason: str
    expires_at: float


class HostPolicyUpdate(BaseModel):
    """Request payload to update host security policies."""

    is_read_only: Optional[bool] = None
    environment_tier: Optional[str] = None
    require_confirm_on_write: Optional[bool] = None


@router.get("/summary", response_model=SSHAssetSummary)
async def get_ssh_assets_summary() -> SSHAssetSummary:
    """Retrieve summary of all discovered SSH host configurations."""
    service = get_ssh_asset_service()
    try:
        return service.get_summary()
    except Exception as e:
        logger.error("Failed to load SSH summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load SSH assets: {e}") from e


@router.get("/probe/{host_alias}", response_model=SSHProbeResult)
async def probe_ssh_host(
    host_alias: str,
    timeout: Optional[float] = Query(default=3.0, ge=0.5, le=10.0),
) -> SSHProbeResult:
    """Probe network connectivity to a specific SSH host."""
    service = get_ssh_asset_service()
    try:
        return await service.probe_host(host_alias, timeout_seconds=timeout or 3.0)
    except Exception as e:
        logger.error("Failed to probe host %s: %s", host_alias, e)
        raise HTTPException(status_code=500, detail=f"Failed to probe host: {e}") from e


@router.post("/execute", response_model=SSHCommandResult)
async def execute_ssh_command(payload: SSHCommandPayload) -> SSHCommandResult:
    """Execute a remote shell command with read-only and break-glass gates."""
    service = get_ssh_asset_service()
    try:
        return await service.execute_remote_command(
            host_alias=payload.host_alias,
            command=payload.command,
            timeout_seconds=payload.timeout_seconds,
            allow_high_risk=payload.allow_high_risk,
            break_glass_token=payload.break_glass_token,
        )
    except Exception as e:
        logger.error("Failed executing SSH command on %s: %s", payload.host_alias, e)
        raise HTTPException(status_code=500, detail=f"Failed executing SSH command: {e}") from e


@router.post("/break-glass/request", response_model=BreakGlassResponse)
async def request_break_glass_token(request: BreakGlassRequest) -> BreakGlassResponse:
    """Request a single-use break-glass token for an authorized state mutation."""
    service = get_ssh_asset_service()
    host = service.get_host(request.host_alias)
    if not host:
        raise HTTPException(status_code=404, detail=f"Host alias '{request.host_alias}' not found")

    try:
        token_data = service.change_window.issue_break_glass_token(
            host_alias=request.host_alias,
            command=request.command,
            reason=request.reason,
            ttl_seconds=request.ttl_seconds,
        )
        return BreakGlassResponse(
            token=token_data.token,
            host_alias=token_data.host_alias,
            reason=token_data.reason,
            expires_at=token_data.expires_at,
        )
    except Exception as e:
        logger.error("Failed to issue break-glass token: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to issue token: {e}") from e


@router.patch("/host/{host_alias}/policy")
async def update_host_policy(host_alias: str, update: HostPolicyUpdate) -> dict[str, str]:
    """Update read-only mode and environment tier for a host."""
    service = get_ssh_asset_service()
    updated = service.update_host_policy(
        host_alias,
        is_read_only=update.is_read_only,
        environment_tier=update.environment_tier,
        require_confirm_on_write=update.require_confirm_on_write,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Host alias '{host_alias}' not found")
    return {"status": "ok", "host_alias": host_alias}
