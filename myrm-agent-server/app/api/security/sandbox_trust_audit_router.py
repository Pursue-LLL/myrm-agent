"""FastAPI router for Sandbox Trust Transparency and Security Isolation Audit Card.

[INPUT]
FastAPI APIRouter, response dependencies, sandbox trust audit service and schemas.

[OUTPUT]
router: API endpoints exposing sandbox isolation grade, egress audit summary, and trust audit card.

[POS]
Router for runtime container isolation integrity metrics and transparency audit card generation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.sandbox_trust_audit import (
    GetBoundaryCardRequest,
    GetTrustBadgeRequest,
    PermissionBoundaryCardResponse,
    SandboxHealthAuditReportResponse,
    SandboxHealthAuditRequest,
    SandboxTrustBadgeResponse,
)
from app.services.security.sandbox_trust_audit_service import (
    SandboxTrustAuditService,
    get_sandbox_trust_audit_service,
)

router = APIRouter(prefix="/sandbox-trust-audit", tags=["sandbox-trust-audit"])


@router.post(
    "/audit",
    response_model=SandboxHealthAuditReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute sandbox health self-audit and escape resistance scan",
)
def run_environment_audit(
    request: SandboxHealthAuditRequest,
    service: SandboxTrustAuditService = Depends(get_sandbox_trust_audit_service),
) -> SandboxHealthAuditReportResponse:
    """Run diagnostics verifying filesystem containment, environment secret sanitization, and egress watchdog."""
    try:
        return service.run_audit(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid isolation parameter: {exc}",
        ) from exc


@router.post(
    "/badge",
    response_model=SandboxTrustBadgeResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate dynamic sandbox trust level badge for UI presentation",
)
def get_trust_badge(
    request: GetTrustBadgeRequest,
    service: SandboxTrustAuditService = Depends(get_sandbox_trust_audit_service),
) -> SandboxTrustBadgeResponse:
    """Compute visual trust badge indicating container boundary strength and audit rating."""
    try:
        return service.get_trust_badge(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid isolation level: {exc}",
        ) from exc


@router.post(
    "/boundary-card",
    response_model=PermissionBoundaryCardResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate interactive permission hot-boundary transparency card",
)
def get_boundary_card(
    request: GetBoundaryCardRequest,
    service: SandboxTrustAuditService = Depends(get_sandbox_trust_audit_service),
) -> PermissionBoundaryCardResponse:
    """Produce boundary card detailing allowed sandbox paths vs strictly protected host paths."""
    try:
        return service.get_boundary_card(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid isolation level: {exc}",
        ) from exc
