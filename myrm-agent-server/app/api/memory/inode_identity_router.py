"""FastAPI router for directory inode identity resolution and sync arbitration.

[POS]
HTTP boundary for directory physical device/inode resolution, directory move/rename
detection, and double-sync prevention during workspace memory ingestion.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.inode_identity
- app.services.memory.inode_identity.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.inode_identity import (
    InodeIdentityHealthResponse,
    ResolveIdentityRequest,
    ResolveIdentityResponse,
    VerifySyncRequest,
    VerifySyncResponse,
)
from app.services.memory.inode_identity import (
    InodeIdentityProvider,
    get_inode_identity_provider,
)

router = APIRouter(prefix="/inode-identity", tags=["Directory Inode Identity"])


@router.post(
    "/resolve",
    response_model=ResolveIdentityResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve physical device and inode identity for a directory path",
)
async def resolve_directory_identity(
    request: ResolveIdentityRequest,
    provider: Annotated[InodeIdentityProvider, Depends(get_inode_identity_provider)],
) -> ResolveIdentityResponse:
    """Probes host filesystem for device and inode metadata, following symlinks."""
    return provider.resolve(request)


@router.post(
    "/verify-sync",
    response_model=VerifySyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Arbitrate directory identity against recorded workspaces before sync",
)
async def verify_sync_directory(
    request: VerifySyncRequest,
    provider: Annotated[InodeIdentityProvider, Depends(get_inode_identity_provider)],
) -> VerifySyncResponse:
    """Verifies workspace physical identity to prevent double-sync or detect moves."""
    return provider.verify_sync(request)


@router.get(
    "/health",
    response_model=InodeIdentityHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint for inode identity subsystem",
)
async def inode_identity_health() -> InodeIdentityHealthResponse:
    """Returns current health status for inode identity subsystem."""
    return InodeIdentityHealthResponse()
