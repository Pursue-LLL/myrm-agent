"""API router for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- TrustDirectoryRequest, UntrustDirectoryRequest, ResolveDirectoryTrustRequest.

[OUTPUT]
- TrustDirectoryResponse, UntrustDirectoryResponse, ListTrustedDirectoriesResponse, ResolvedDirectoryTrustDto.

[POS]
- Security router mounted under /security/directory-trust-gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.directory_trust_gate import (
    ListTrustedDirectoriesResponse,
    ResolvedDirectoryTrustDto,
    ResolveDirectoryTrustRequest,
    TrustDirectoryRequest,
    TrustDirectoryResponse,
    UntrustDirectoryRequest,
    UntrustDirectoryResponse,
)
from app.services.security.directory_trust_gate_service import (
    DirectoryTrustGateService,
    get_directory_trust_gate_service,
)

router = APIRouter(
    prefix="/directory-trust-gate", tags=["directory-trust-gate"]
)


@router.post("/trust", response_model=TrustDirectoryResponse)
async def trust_directory(
    request: TrustDirectoryRequest,
    service: DirectoryTrustGateService = Depends(
        get_directory_trust_gate_service
    ),
) -> TrustDirectoryResponse:
    """Register a workspace directory path as trusted for configuration and remote memory."""
    return service.trust_directory(request)


@router.post("/untrust", response_model=UntrustDirectoryResponse)
async def untrust_directory(
    request: UntrustDirectoryRequest,
    service: DirectoryTrustGateService = Depends(
        get_directory_trust_gate_service
    ),
) -> UntrustDirectoryResponse:
    """Revoke trust from a directory boundary."""
    return service.untrust_directory(request)


@router.get("/trusted", response_model=ListTrustedDirectoriesResponse)
async def list_trusted_directories(
    service: DirectoryTrustGateService = Depends(
        get_directory_trust_gate_service
    ),
) -> ListTrustedDirectoriesResponse:
    """Retrieve all registered trusted directory boundaries."""
    return service.list_trusted()


@router.post("/resolve", response_model=ResolvedDirectoryTrustDto)
async def resolve_directory_trust(
    request: ResolveDirectoryTrustRequest,
    service: DirectoryTrustGateService = Depends(
        get_directory_trust_gate_service
    ),
) -> ResolvedDirectoryTrustDto:
    """Perform single-point resolution of memory config and directory trust gating."""
    return service.resolve_directory_trust(request)
