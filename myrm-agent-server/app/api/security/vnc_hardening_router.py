"""
[POS] app/api/security/vnc_hardening_router.py
[INPUT] fastapi, app.schemas.vnc_hardening, app.services.security.vnc_hardening_service
[OUTPUT] vnc_hardening_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.core.security.vnc_hardening import VncSecurityError

from app.schemas.vnc_hardening import (
    AuditRawVncCommandRequestDTO,
    EvaluatePasswordRequestDTO,
    EvaluatePasswordResponseDTO,
    GenerateSecurePasswordRequestDTO,
    GenerateSecurePasswordResponseDTO,
    SanitizeVncLaunchConfigRequestDTO,
    VncHardenedLaunchSpecDTO,
    VncHardeningAuditReportDTO,
)
from app.services.security.vnc_hardening_service import (
    VncHardeningService,
    get_vnc_hardening_service,
)

router = APIRouter(
    prefix="/vnc-hardening",
    tags=["VNC Loopback Bind & Rfbauth Hardening"],
)


@router.post(
    "/sanitize",
    response_model=VncHardenedLaunchSpecDTO,
    summary="Sanitize and harden x11vnc launch parameters",
)
def sanitize_vnc_launch_config(
    request: SanitizeVncLaunchConfigRequestDTO,
    service: VncHardeningService = Depends(get_vnc_hardening_service),
) -> VncHardenedLaunchSpecDTO:
    """Enforce loopback binding (-localhost), eliminate conflicting -nopw, and mandate rfbauth."""
    try:
        return service.sanitize_launch_config(request)
    except (VncSecurityError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/audit",
    response_model=VncHardeningAuditReportDTO,
    summary="Audit existing raw x11vnc invocation for security exposures",
)
def audit_raw_vnc_command(
    request: AuditRawVncCommandRequestDTO,
    service: VncHardeningService = Depends(get_vnc_hardening_service),
) -> VncHardeningAuditReportDTO:
    """Evaluate x11vnc command line flags and generate compliance assessment report."""
    return service.audit_raw_command(request)


@router.post(
    "/generate-password",
    response_model=GenerateSecurePasswordResponseDTO,
    summary="Generate high-entropy random password suitable for VNC rfbauth",
)
def generate_secure_password(
    request: GenerateSecurePasswordRequestDTO,
    service: VncHardeningService = Depends(get_vnc_hardening_service),
) -> GenerateSecurePasswordResponseDTO:
    """Generate a compliant high-entropy random password for VNC credential store."""
    return service.generate_secure_password(request)


@router.post(
    "/evaluate-password",
    response_model=EvaluatePasswordResponseDTO,
    summary="Evaluate password strength against baseline policy",
)
def evaluate_password(
    request: EvaluatePasswordRequestDTO,
    service: VncHardeningService = Depends(get_vnc_hardening_service),
) -> EvaluatePasswordResponseDTO:
    """Verify that password satisfies length and complexity rules."""
    return service.evaluate_password(request)
