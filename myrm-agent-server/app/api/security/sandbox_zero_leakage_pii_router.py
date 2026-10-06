"""API router for Physical Sandbox Zero-Leakage Attestation and PII Firewall Suite.

[POS] app/api/security/sandbox_zero_leakage_pii_router.py
[INPUT] app/schemas/sandbox_zero_leakage_pii.py, app/services/security/sandbox_zero_leakage_pii_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.sandbox_zero_leakage_pii import (
    AgentProfileSignatureResponse,
    AuditOperatorRequest,
    AuditOperatorResponse,
    IssueAttestationRequest,
    ScanPiiRequest,
    ScanPiiResponse,
    SignProfileRequest,
    VerifyAttestationRequest,
    VerifyAttestationResponse,
    VerifyProfileRequest,
    VerifyProfileResponse,
    ZeroLeakageAttestationResponse,
)
from app.services.security.sandbox_zero_leakage_pii_service import (
    SandboxZeroLeakagePiiService,
    get_sandbox_zero_leakage_pii_service,
)

router = APIRouter(prefix="/sandbox-zero-leakage", tags=["sandbox-zero-leakage-pii"])


@router.post("/attestation/issue", response_model=ZeroLeakageAttestationResponse)
async def issue_sandbox_attestation(
    req: IssueAttestationRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> ZeroLeakageAttestationResponse:
    """Issue cryptographic zero-cross-tenant leakage attestation proof."""
    return service.issue_attestation(req)


@router.post("/attestation/verify", response_model=VerifyAttestationResponse)
async def verify_sandbox_attestation(
    req: VerifyAttestationRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> VerifyAttestationResponse:
    """Verify authenticity and tamper-resistance of an attestation proof."""
    return service.verify_attestation(req)


@router.post("/pii/scan-redact", response_model=ScanPiiResponse)
async def scan_and_redact_pii(
    req: ScanPiiRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> ScanPiiResponse:
    """Scan and redact high-risk child privacy, contact coordinates, and financial numbers."""
    return service.scan_pii(req)


@router.post("/transparency/audit", response_model=AuditOperatorResponse)
async def audit_operator_transparency(
    req: AuditOperatorRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> AuditOperatorResponse:
    """Audit third-party hosting operator across 4 dimensions: identity, model, storage, and code."""
    return service.audit_operator(req)


@router.post("/profile/sign", response_model=AgentProfileSignatureResponse)
async def sign_agent_profile(
    req: SignProfileRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> AgentProfileSignatureResponse:
    """Issue official cryptographic signature for an agent profile."""
    return service.sign_profile(req)


@router.post("/profile/verify", response_model=VerifyProfileResponse)
async def verify_agent_profile(
    req: VerifyProfileRequest,
    service: SandboxZeroLeakagePiiService = Depends(get_sandbox_zero_leakage_pii_service),
) -> VerifyProfileResponse:
    """Verify digital signature and prompt integrity of an agent profile."""
    return service.verify_profile(req)
