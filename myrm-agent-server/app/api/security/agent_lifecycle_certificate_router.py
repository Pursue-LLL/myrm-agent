"""
[POS] app/api/security/agent_lifecycle_certificate_router.py
[INPUT] app/schemas/agent_lifecycle_certificate.py, app/services/security/agent_lifecycle_certificate_service.py
[OUTPUT] router

FastAPI router for AI Agent digital certificate lifecycle management, pre-execution verification gates,
and emergency revocation (CRL).

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.agent_lifecycle_certificate import (
    AgentCertificateResponse,
    CertificateHealthDashboardResponse,
    CrlSnapshotResponse,
    EmergencyRevocationRequest,
    MintAgentCertificateRequest,
    PreflightVerificationRequest,
    PreflightVerificationResponse,
    RevocationRecordResponse,
)
from app.services.security.agent_lifecycle_certificate_service import (
    AgentLifecycleCertificateService,
    get_agent_lifecycle_certificate_service,
)

router = APIRouter(
    prefix="/agent-certs",
    tags=["Agent Digital Certificate & Emergency Revocation"],
)


@router.post(
    "/mint",
    response_model=AgentCertificateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint and cryptographically sign an agent digital certificate",
)
def mint_certificate(
    request: MintAgentCertificateRequest,
) -> AgentCertificateResponse:
    """Issue a new X.509/SM2 digital certificate for an AI agent."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    return service.mint_certificate(request)


@router.post(
    "/verify-preflight",
    response_model=PreflightVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Pre-execution certificate verification gate before sandbox launch",
)
def verify_preflight(
    request: PreflightVerificationRequest,
) -> PreflightVerificationResponse:
    """Check certificate cryptographic signature, expiration dates, and revocation status."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    return service.verify_preflight(request)


@router.post(
    "/revoke",
    response_model=RevocationRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Emergency revoke an agent digital certificate and broadcast to CRL",
)
def emergency_revoke(
    request: EmergencyRevocationRequest,
) -> RevocationRecordResponse:
    """Instantly invalidate a compromised agent certificate and push to global CRL."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    record = service.emergency_revoke(request)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{request.cert_id}' not found.",
        )
    return record


@router.get(
    "/crl/snapshot",
    response_model=CrlSnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active Certificate Revocation List (CRL) snapshot",
)
def get_crl_snapshot() -> CrlSnapshotResponse:
    """Fetch current list of revoked certificate serial numbers and revocation reasons."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    return service.get_crl_snapshot()


@router.get(
    "/health/dashboard",
    response_model=CertificateHealthDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect certificate health, expiration countdown, and renewal warnings",
)
def get_health_dashboard(
    simulated_current_time: Optional[float] = Query(
        default=None, description="Optional timestamp override for diagnostic testing."
    ),
) -> CertificateHealthDashboardResponse:
    """Retrieve health statistics and 30-day/7-day expiration countdown warnings."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    return service.get_health_dashboard(current_time=simulated_current_time)


@router.get(
    "/{cert_id}",
    response_model=AgentCertificateResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve agent certificate details by certificate ID",
)
def get_certificate(
    cert_id: str,
) -> AgentCertificateResponse:
    """Look up an issued agent certificate by its unique cert_id."""
    service: AgentLifecycleCertificateService = get_agent_lifecycle_certificate_service()
    cert = service.get_certificate(cert_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{cert_id}' not found.",
        )
    return cert
