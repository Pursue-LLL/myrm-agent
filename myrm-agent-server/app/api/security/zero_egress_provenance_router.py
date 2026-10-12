"""API router for Enterprise Zero-Egress Audit Ledger & Asset Provenance Suite.

[INPUT]
- RecordAuditEventRequest, GenerateZeroEgressCertificateRequest, CreateAssetProvenanceRequest, VerifyAssetProvenanceRequest.

[OUTPUT]
- Endpoints for tamper-evident audit logging, chain verification, export,
  zero-egress certification, and asset provenance creation/verification.

[POS]
- Server API. Mounted under /api/v1/security/zero-egress-provenance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.zero_egress_provenance import (
    AssetProvenanceDossierDto,
    AuditLedgerRecordDto,
    CreateAssetProvenanceRequest,
    GenerateZeroEgressCertificateRequest,
    RecordAuditEventRequest,
    VerifyAssetProvenanceRequest,
    VerifyAssetProvenanceResponse,
    VerifyLedgerIntegrityResponse,
    ZeroEgressAttestationCertificateDto,
)
from app.services.security.zero_egress_provenance_service import (
    get_zero_egress_provenance_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zero-egress-provenance", tags=["zero-egress-provenance"])


@router.post("/audit/record", response_model=AuditLedgerRecordDto)
def record_audit_event(request: RecordAuditEventRequest) -> AuditLedgerRecordDto:
    """Record a cross-system action into the tamper-evident hash-chained audit ledger."""
    service = get_zero_egress_provenance_service()
    return service.record_event(request)


@router.get("/audit/verify", response_model=VerifyLedgerIntegrityResponse)
def verify_audit_ledger() -> VerifyLedgerIntegrityResponse:
    """Validate non-repudiation cryptographic hash chain across all stored ledger records."""
    service = get_zero_egress_provenance_service()
    return service.verify_ledger()


@router.get("/audit/export", response_model=list[AuditLedgerRecordDto])
def export_audit_ledger() -> list[AuditLedgerRecordDto]:
    """Export complete chained audit ledger for HIPAA/SOC2 compliance examination."""
    service = get_zero_egress_provenance_service()
    return service.export_ledger()


@router.post("/certificate/generate", response_model=ZeroEgressAttestationCertificateDto)
def generate_zero_egress_certificate(
    request: GenerateZeroEgressCertificateRequest,
) -> ZeroEgressAttestationCertificateDto:
    """Issue a signed compliance certificate attesting that session data remains strictly confined."""
    service = get_zero_egress_provenance_service()
    return service.generate_certificate(request)


@router.post("/provenance/create", response_model=AssetProvenanceDossierDto)
def create_asset_provenance(request: CreateAssetProvenanceRequest) -> AssetProvenanceDossierDto:
    """Create a cryptographic provenance record guaranteeing non-infringement tracking for generated code."""
    service = get_zero_egress_provenance_service()
    return service.create_provenance(request)


@router.post("/provenance/verify", response_model=VerifyAssetProvenanceResponse)
def verify_asset_provenance(request: VerifyAssetProvenanceRequest) -> VerifyAssetProvenanceResponse:
    """Validate that candidate content matches its registered IP provenance dossier digest."""
    service = get_zero_egress_provenance_service()
    return service.verify_provenance(request)
