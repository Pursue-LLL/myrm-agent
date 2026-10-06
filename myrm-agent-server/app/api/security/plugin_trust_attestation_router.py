"""API router for Plugin Trust Chain and Dynamic Capability Attestation.

[POS] app/api/security/plugin_trust_attestation_router.py
[INPUT] app/schemas/plugin_trust_attestation.py, app/services/security/plugin_trust_attestation_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.schemas.plugin_trust_attestation import (
    AttestationTokenResponse,
    IssueAttestationTokenRequest,
    SignedPluginPackageResponse,
    SignPluginPackageRequest,
    ValidateOperationRequest,
    ValidateOperationResponse,
    VerifyPluginPackageRequest,
    VerifyPluginPackageResponse,
)
from app.services.security.plugin_trust_attestation_service import (
    PluginTrustAttestationService,
    get_plugin_trust_attestation_service,
)

router = APIRouter(prefix="/plugin-trust", tags=["plugin-trust-attestation"])


@router.post("/sign", response_model=SignedPluginPackageResponse)
async def sign_plugin_package(
    req: SignPluginPackageRequest,
    service: PluginTrustAttestationService = Depends(get_plugin_trust_attestation_service),
) -> SignedPluginPackageResponse:
    """Cryptographically sign a plugin release package using official root key."""
    return service.sign_package(req)


@router.post("/verify", response_model=VerifyPluginPackageResponse)
async def verify_plugin_package(
    req: VerifyPluginPackageRequest,
    service: PluginTrustAttestationService = Depends(get_plugin_trust_attestation_service),
) -> VerifyPluginPackageResponse:
    """Verify package integrity, HMAC signature, and trust tier."""
    return service.verify_package(req)


@router.post("/tokens", response_model=AttestationTokenResponse)
async def issue_attestation_token(
    req: IssueAttestationTokenRequest,
    service: PluginTrustAttestationService = Depends(get_plugin_trust_attestation_service),
) -> AttestationTokenResponse:
    """Issue a dynamic time-bound capability proof token for runtime sandbox."""
    return service.issue_token(req)


@router.post("/validate-operation", response_model=ValidateOperationResponse)
async def validate_plugin_operation(
    req: ValidateOperationRequest,
    service: PluginTrustAttestationService = Depends(get_plugin_trust_attestation_service),
) -> ValidateOperationResponse:
    """Validate runtime domain and shell permissions against an active attestation token."""
    return service.validate_operation(req)


@router.post("/compute-digest")
async def compute_payload_digest(
    files: dict[str, str] = Body(..., description="Mapping of relative filenames to file contents"),
    service: PluginTrustAttestationService = Depends(get_plugin_trust_attestation_service),
) -> dict[str, str]:
    """Compute deterministic SHA-256 digest across payload files."""
    digest = service.compute_files_digest(files)
    return {"digest": digest}
