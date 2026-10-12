"""
[POS] app/api/security/code_signing_gate_router.py
[INPUT] app.schemas.code_signing_gate, app.services.security.code_signing_gate_service
[OUTPUT] router

FastAPI router for Developer Identity Attestation & Agent Package Code Signing Gate Suite.
Exposes REST endpoints to build signed packages, verify package code signatures and asset integrity,
configure enterprise supply chain trust policies, and revoke compromised certificates.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.code_signing_gate import (
    CodeSigningGateMetricsResponse,
    PackageSignRequest,
    PackageVerifyRequest,
    PackageVerifyResponse,
    RevokeCertificateRequest,
    SignedPackageResponse,
    TrustPolicyResponse,
    TrustPolicyUpdateRequest,
)
from app.services.security.code_signing_gate_service import (
    CodeSigningGateService,
    get_code_signing_gate_service,
)

router = APIRouter(
    prefix="/code-signing",
    tags=["Code Signing & Supply Chain Trust Gate"],
)


@router.post(
    "/sign-package",
    response_model=SignedPackageResponse,
    status_code=status.HTTP_200_OK,
    summary="Construct cryptographic manifest and sign agent package using developer private key",
)
def sign_package(
    request: PackageSignRequest,
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> SignedPackageResponse:
    """Build canonical package manifest digests and compute Ed25519 detached digital signature."""
    return service.sign_package(request)


@router.post(
    "/verify-package",
    response_model=PackageVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify package code signature, asset digest integrity, and supply chain trust",
)
def verify_package(
    request: PackageVerifyRequest,
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> PackageVerifyResponse:
    """Validate detached signature, check asset hashes against manifest, and evaluate active enterprise policy."""
    return service.verify_package(request)


@router.get(
    "/policy",
    response_model=TrustPolicyResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect active enterprise supply chain trust policy",
)
def get_policy(
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> TrustPolicyResponse:
    """Retrieve currently active enterprise policy (STRICT_ENTERPRISE_ONLY, VERIFIED_CA_ONLY, etc.)."""
    return service.get_policy()


@router.put(
    "/policy",
    response_model=TrustPolicyResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure active enterprise supply chain trust policy",
)
def set_policy(
    request: TrustPolicyUpdateRequest,
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> TrustPolicyResponse:
    """Update organizational policy governing external and unsigned agent/skill packages."""
    return service.set_policy(request)


@router.post(
    "/revoke-cert",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
    summary="Revoke compromised developer certificate serial",
)
def revoke_certificate(
    request: RevokeCertificateRequest,
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> dict[str, bool]:
    """Add certificate serial to CRL revocation blacklist."""
    was_revoked = service.revoke_certificate(request.cert_serial)
    return {"revoked": was_revoked}


@router.get(
    "/metrics",
    response_model=CodeSigningGateMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect supply chain code signing telemetry metrics",
)
def get_metrics(
    service: CodeSigningGateService = Depends(get_code_signing_gate_service),
) -> CodeSigningGateMetricsResponse:
    """Retrieve cumulative statistics across package verifications, tampered blocks, and signature errors."""
    return service.get_metrics()
