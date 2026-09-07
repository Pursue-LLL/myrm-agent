"""API routes for SSH Host Asset Management and Probing.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException, Query
- app.services.ssh_vault::SSHAssetService, SSHAssetSummary, SSHProbeResult

[OUTPUT]
- router: FastAPI APIRouter instance

[POS]
API endpoints in app/api/ssh_vault/.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.ssh_vault.models import SSHAssetSummary, SSHProbeResult
from app.services.ssh_vault.service import SSHAssetService

logger = logging.getLogger("myrm.api.ssh_vault")

router = APIRouter(prefix="/api/ssh-vault", tags=["ssh-vault"])

_ssh_service = SSHAssetService()


@router.get("/summary", response_model=SSHAssetSummary)
async def get_ssh_assets_summary() -> SSHAssetSummary:
    """Retrieve summary of all discovered SSH host configurations."""
    try:
        return _ssh_service.get_summary()
    except Exception as e:
        logger.error("Failed to load SSH summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load SSH assets: {e}") from e

@router.get("/probe/{host_alias}", response_model=SSHProbeResult)
async def probe_ssh_host(
    host_alias: str,
    timeout: Optional[float] = Query(default=3.0, ge=0.5, le=10.0),
) -> SSHProbeResult:
    """Probe network connectivity to a specific SSH host."""
    try:
        return await _ssh_service.probe_host(host_alias, timeout_seconds=timeout or 3.0)
    except Exception as e:
        logger.error("Failed to probe host %s: %s", host_alias, e)
        raise HTTPException(status_code=500, detail=f"Failed to probe host: {e}") from e
