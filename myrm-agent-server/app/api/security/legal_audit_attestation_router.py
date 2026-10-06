"""
[POS] app/api/security/legal_audit_attestation_router.py
[INPUT] app/schemas/legal_audit_attestation.py, app/services/security/legal_audit_attestation_service.py
[OUTPUT] router

FastAPI router for legal-grade cryptographic audit, RFC 3161 TSA anchoring, and non-repudiation dossiers.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.legal_audit_attestation import (
    AuditEntryCreateRequest,
    AuditEntryNodeResponse,
    EvidenceDossierPackRequest,
    EvidenceDossierResponse,
    EvidenceDossierVerifyRequest,
    EvidenceDossierVerifyResponse,
    LedgerStatusResponse,
    LegalAuditMetricsResponse,
    TsaAnchorRequest,
    TsaTimestampTokenResponse,
)
from app.services.security.legal_audit_attestation_service import (
    LegalAuditAttestationService,
    get_legal_audit_attestation_service,
)

router = APIRouter(
    prefix="/legal-audit",
    tags=["Legal Audit Attestation & TSA Gateway"],
)


@router.post(
    "/entries",
    response_model=AuditEntryNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an attested action in the append-only Merkle ledger",
)
def record_audit_entry(
    request: AuditEntryCreateRequest,
) -> AuditEntryNodeResponse:
    """Record an agent execution event as an immutable RFC 6962 Merkle leaf node."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    return service.record_entry(request)


@router.post(
    "/tsa-anchor",
    response_model=TsaTimestampTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Anchor Merkle root or digest with RFC 3161 TSA authority",
)
def anchor_tsa(
    request: TsaAnchorRequest,
) -> TsaTimestampTokenResponse:
    """Issue a cryptographic timestamp token from a legal TSA authority (e.g., Guizhou CA)."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    return service.anchor_tsa(request)


@router.post(
    "/dossiers/pack",
    response_model=EvidenceDossierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pack an attested event into a legal anti-repudiation evidence dossier",
)
def pack_evidence_dossier(
    request: EvidenceDossierPackRequest,
) -> EvidenceDossierResponse:
    """Assemble an immutable evidence dossier with inclusion proof, TSA token, and seal."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    dossier = service.pack_dossier(request)
    if dossier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit entry '{request.entry_id}' was not found in the ledger.",
        )
    return dossier


@router.post(
    "/dossiers/verify",
    response_model=EvidenceDossierVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Forensically verify an evidence dossier against cryptographic roots and TSA",
)
def verify_evidence_dossier(
    request: EvidenceDossierVerifyRequest,
) -> EvidenceDossierVerifyResponse:
    """Perform mathematical proof verification and RFC 3161 timestamp checks on a dossier."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    return service.verify_dossier(request)


@router.get(
    "/ledger/status",
    response_model=LedgerStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current state and root hash of the Merkle audit ledger",
)
def get_ledger_status() -> LedgerStatusResponse:
    """Query current total entry count and cryptographic Merkle root hash."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    return service.get_ledger_status()


@router.get(
    "/metrics",
    response_model=LegalAuditMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve operational metrics for legal audit and attestation",
)
def get_metrics() -> LegalAuditMetricsResponse:
    """Retrieve counts of recorded entries, packed dossiers, and verified records."""
    service: LegalAuditAttestationService = get_legal_audit_attestation_service()
    return service.get_metrics()
