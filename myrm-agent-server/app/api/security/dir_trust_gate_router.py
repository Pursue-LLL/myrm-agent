"""API router for Directory Trust Gate.

[INPUT]
- app.services.security.dir_trust_gate_service::DirTrustGateService (POS: Manages directory authorization lifecycle)

[OUTPUT]
- APIRouter handling /dir-trust-gate endpoints for evaluate, trust, untrust, and list.

[POS]
HTTP routing layer for Directory Trust Gate security boundaries.
"""

from fastapi import APIRouter, Depends

from app.schemas.dir_trust_gate import (
    DirectoryTrustActionRequest,
    DirectoryTrustActionResponse,
    DirectoryTrustEvaluateRequest,
    DirectoryTrustEvaluateResponse,
    DirectoryTrustListResponse,
)
from app.services.security.dir_trust_gate_service import (
    DirTrustGateService,
    get_dir_trust_gate_service,
)

router = APIRouter(prefix="/dir-trust-gate", tags=["security", "dir-trust-gate"])


@router.post("/evaluate", response_model=DirectoryTrustEvaluateResponse)
async def evaluate_directory_trust(
    request: DirectoryTrustEvaluateRequest,
    service: DirTrustGateService = Depends(get_dir_trust_gate_service),
) -> DirectoryTrustEvaluateResponse:
    """Evaluate repository settings against directory trust boundaries."""
    return service.evaluate_directory(request)


@router.post("/trust", response_model=DirectoryTrustActionResponse)
async def trust_directory(
    request: DirectoryTrustActionRequest,
    service: DirTrustGateService = Depends(get_dir_trust_gate_service),
) -> DirectoryTrustActionResponse:
    """Explicitly authorize and trust a workspace directory."""
    return service.trust_directory(request.directory, reason=request.reason)


@router.post("/untrust", response_model=DirectoryTrustActionResponse)
async def untrust_directory(
    request: DirectoryTrustActionRequest,
    service: DirTrustGateService = Depends(get_dir_trust_gate_service),
) -> DirectoryTrustActionResponse:
    """Revoke authorization from a workspace directory."""
    return service.untrust_directory(request.directory)


@router.get("/list", response_model=DirectoryTrustListResponse)
async def list_trusted_directories(
    service: DirTrustGateService = Depends(get_dir_trust_gate_service),
) -> DirectoryTrustListResponse:
    """List all explicitly trusted workspace directories."""
    return service.list_trusted_directories()
