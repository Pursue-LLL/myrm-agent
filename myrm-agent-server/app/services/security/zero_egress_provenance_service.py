"""Enterprise Zero-Egress Audit Ledger & Asset Provenance Service.

[INPUT]
- RecordAuditEventRequest, GenerateZeroEgressCertificateRequest, CreateAssetProvenanceRequest, VerifyAssetProvenanceRequest.

[OUTPUT]
- AuditLedgerRecordDto, VerifyLedgerIntegrityResponse, ZeroEgressAttestationCertificateDto,
  AssetProvenanceDossierDto, VerifyAssetProvenanceResponse.

[POS]
- Server security service. Wraps harness ImmutableAuditLedgerEngine and GenerativeAssetProvenanceEngine
  to enforce non-repudiation audit logging, zero-data-retention certification, and IP asset provenance.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.zero_egress_provenance import (
    AssetProvenanceDossier,
    AttestationLevel,
    AuditLedgerRecord,
    EgressBoundaryState,
    GenerativeAssetProvenanceEngine,
    ImmutableAuditLedgerEngine,
    IPCleanlinessTier,
    ZeroEgressAttestationCertificate,
)

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

logger = logging.getLogger(__name__)


def _to_record_dto(rec: AuditLedgerRecord) -> AuditLedgerRecordDto:
    return AuditLedgerRecordDto(
        record_id=rec.record_id,
        sequence_number=rec.sequence_number,
        timestamp_utc=rec.timestamp_utc,
        actor=rec.actor,
        action_type=rec.action_type,
        resource_target=rec.resource_target,
        input_sha256=rec.input_sha256,
        output_sha256=rec.output_sha256,
        boundary_state=rec.boundary_state.value,
        previous_record_hash=rec.previous_record_hash,
        current_record_hash=rec.current_record_hash,
        compliance_standard=rec.compliance_standard,
    )


def _to_cert_dto(cert: ZeroEgressAttestationCertificate) -> ZeroEgressAttestationCertificateDto:
    return ZeroEgressAttestationCertificateDto(
        certificate_id=cert.certificate_id,
        session_id=cert.session_id,
        tenant_id=cert.tenant_id,
        sandbox_id=cert.sandbox_id,
        attestation_level=cert.attestation_level.value,
        zero_data_retention_guaranteed=cert.zero_data_retention_guaranteed,
        no_model_training_guaranteed=cert.no_model_training_guaranteed,
        environment_digest_sha256=cert.environment_digest_sha256,
        signature=cert.signature,
        issued_at_iso=cert.issued_at_iso,
        issuer=cert.issuer,
    )


def _to_dossier_dto(dossier: AssetProvenanceDossier) -> AssetProvenanceDossierDto:
    return AssetProvenanceDossierDto(
        dossier_id=dossier.dossier_id,
        asset_id=dossier.asset_id,
        asset_name=dossier.asset_name,
        media_type=dossier.media_type,
        content_sha256=dossier.content_sha256,
        session_id=dossier.session_id,
        origin_prompt_sha256=dossier.origin_prompt_sha256,
        foundation_model_id=dossier.foundation_model_id,
        ip_tier=dossier.ip_tier.value,
        license_type=dossier.license_type,
        digital_signature=dossier.digital_signature,
        created_at_iso=dossier.created_at_iso,
    )


def _from_dossier_dto(dto: AssetProvenanceDossierDto) -> AssetProvenanceDossier:
    try:
        tier = IPCleanlinessTier(dto.ip_tier)
    except ValueError:
        tier = IPCleanlinessTier.ENTERPRISE_INDEMNIFIED

    return AssetProvenanceDossier(
        dossier_id=dto.dossier_id,
        asset_id=dto.asset_id,
        asset_name=dto.asset_name,
        media_type=dto.media_type,
        content_sha256=dto.content_sha256,
        session_id=dto.session_id,
        origin_prompt_sha256=dto.origin_prompt_sha256,
        foundation_model_id=dto.foundation_model_id,
        ip_tier=tier,
        license_type=dto.license_type,
        digital_signature=dto.digital_signature,
        created_at_iso=dto.created_at_iso,
    )


class ZeroEgressProvenanceService:
    """Service governing immutable audit ledger recording and asset IP provenance tracking."""

    def __init__(
        self,
        ledger: ImmutableAuditLedgerEngine | None = None,
        provenance: GenerativeAssetProvenanceEngine | None = None,
    ) -> None:
        self._ledger = ledger or ImmutableAuditLedgerEngine()
        self._provenance = provenance or GenerativeAssetProvenanceEngine()

    def record_event(self, req: RecordAuditEventRequest) -> AuditLedgerRecordDto:
        """Record a cross-system agent execution event into the immutable hash-chained ledger."""
        try:
            b_state = EgressBoundaryState(req.boundary_state)
        except ValueError:
            b_state = EgressBoundaryState.SANDBOX_CONFINED

        rec = self._ledger.record_event(
            actor=req.actor,
            action_type=req.action_type,
            resource_target=req.resource_target,
            input_payload=req.input_payload,
            output_payload=req.output_payload,
            boundary_state=b_state,
        )
        return _to_record_dto(rec)

    def verify_ledger(self) -> VerifyLedgerIntegrityResponse:
        """Validate non-repudiation cryptographic hash chain across all stored ledger records."""
        is_intact = self._ledger.verify_chain_integrity(raise_on_error=False)
        total = self._ledger.record_count
        note = (
            f"Successfully validated cryptographic hash chain across {total} records."
            if is_intact
            else "Hash chain mismatch or record tampering detected."
        )
        return VerifyLedgerIntegrityResponse(
            is_intact=is_intact,
            total_records=total,
            audit_notes=note,
        )

    def export_ledger(self) -> list[AuditLedgerRecordDto]:
        """Export all chained records for HIPAA and SOC2 compliance audits."""
        return [_to_record_dto(r) for r in self._ledger.export_ledger()]

    def generate_certificate(
        self, req: GenerateZeroEgressCertificateRequest
    ) -> ZeroEgressAttestationCertificateDto:
        """Issue an immutable zero-egress attestation certificate."""
        try:
            level = AttestationLevel(req.attestation_level)
        except ValueError:
            level = AttestationLevel.ENTERPRISE_ZERO_EGRESS

        cert = self._provenance.generate_zero_egress_certificate(
            session_id=req.session_id,
            tenant_id=req.tenant_id,
            sandbox_id=req.sandbox_id,
            attestation_level=level,
        )
        return _to_cert_dto(cert)

    def create_provenance(self, req: CreateAssetProvenanceRequest) -> AssetProvenanceDossierDto:
        """Create IP provenance dossier guaranteeing non-infringement tracking for generated assets."""
        try:
            tier = IPCleanlinessTier(req.ip_tier)
        except ValueError:
            tier = IPCleanlinessTier.ENTERPRISE_INDEMNIFIED

        dossier = self._provenance.generate_provenance_dossier(
            asset_id=req.asset_id,
            asset_name=req.asset_name,
            media_type=req.media_type,
            content=req.content,
            session_id=req.session_id,
            prompt_text=req.prompt_text,
            foundation_model_id=req.foundation_model_id,
            license_type=req.license_type,
            ip_tier=tier,
        )
        return _to_dossier_dto(dossier)

    def verify_provenance(self, req: VerifyAssetProvenanceRequest) -> VerifyAssetProvenanceResponse:
        """Verify whether candidate content digest matches the registered provenance dossier."""
        domain_dossier = _from_dossier_dto(req.dossier)
        is_verified = self._provenance.verify_asset_provenance(
            dossier=domain_dossier,
            content=req.content,
            raise_on_error=False,
        )
        notes = (
            "Content digest matches declared provenance record."
            if is_verified
            else "Content digest mismatch: content was altered after provenance registration."
        )
        return VerifyAssetProvenanceResponse(
            is_verified=is_verified,
            asset_id=req.dossier.asset_id,
            audit_notes=notes,
        )


_service_instance: ZeroEgressProvenanceService | None = None


def get_zero_egress_provenance_service() -> ZeroEgressProvenanceService:
    """Obtain or initialize singleton ZeroEgressProvenanceService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ZeroEgressProvenanceService()
    return _service_instance
