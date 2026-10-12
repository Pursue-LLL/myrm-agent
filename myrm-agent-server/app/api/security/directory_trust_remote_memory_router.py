"""API router for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- TrustDirectoryRequest, ResolveProjectRemoteRequest.

[OUTPUT]
- TrustDirectoryResponse, CheckDirectoryTrustResponse, ResolveProjectRemoteResponse.

[POS]
- Security router mounted under /security/directory-trust-remote-memory.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.directory_trust_remote_memory import (
    CheckDirectoryTrustResponse,
    ResolveProjectRemoteRequest,
    ResolveProjectRemoteResponse,
    TrustDirectoryRequest,
    TrustDirectoryResponse,
)
from app.services.security.directory_trust_remote_memory_service import (
    DirectoryTrustRemoteMemoryService,
    get_directory_trust_remote_memory_service,
)

router = APIRouter(
    prefix="/directory-trust-remote-memory",
    tags=["directory-trust-remote-memory"],
)


@router.post("/trust", response_model=TrustDirectoryResponse)
async def update_directory_trust(
    request: TrustDirectoryRequest,
    service: DirectoryTrustRemoteMemoryService = Depends(
        get_directory_trust_remote_memory_service
    ),
) -> TrustDirectoryResponse:
    """Add or remove a directory from the trusted registry."""
    return service.set_directory_trust(request)


@router.get("/trust/check", response_model=CheckDirectoryTrustResponse)
async def check_directory_trust(
    directory: str = Query(..., description="Target directory path to inspect"),
    service: DirectoryTrustRemoteMemoryService = Depends(
        get_directory_trust_remote_memory_service
    ),
) -> CheckDirectoryTrustResponse:
    """Check whether a specific directory resides within a trusted root."""
    return service.check_directory_trust(directory)


@router.get("/trust/list", response_model=list[str])
async def list_trusted_directories(
    service: DirectoryTrustRemoteMemoryService = Depends(
        get_directory_trust_remote_memory_service
    ),
) -> list[str]:
    """Retrieve list of all canonical trusted directory roots."""
    return service.list_trusted_directories()


@router.post("/resolve", response_model=ResolveProjectRemoteResponse)
async def resolve_project_remote(
    request: ResolveProjectRemoteRequest,
    service: DirectoryTrustRemoteMemoryService = Depends(
        get_directory_trust_remote_memory_service
    ),
) -> ResolveProjectRemoteResponse:
    """Atomically resolve project memory settings against directory trust gates."""
    return service.resolve_project_remote(request)
