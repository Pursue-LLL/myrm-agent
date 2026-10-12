"""
[POS] app/services/security/agent_lifecycle_certificate_service.py
[INPUT] myrm_agent_harness.core.security.agent_lifecycle_certificate, app.schemas.agent_lifecycle_certificate
[OUTPUT] AgentLifecycleCertificateService, get_agent_lifecycle_certificate_service

Thread-safe service managing AI Agent digital certificates, pre-execution verification gates,
and emergency revocation (CRL) lists.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.agent_lifecycle_certificate import (
    AgentDigitalCertificateSpec,
    AgentLifecycleCertificateSuite,
)
from myrm_agent_harness.core.security.agent_lifecycle_certificate import (
    CertificateStatusEnum as HarnessCertStatusEnum,
)
from myrm_agent_harness.core.security.agent_lifecycle_certificate import (
    RevocationReasonEnum as HarnessRevocationReasonEnum,
)

from app.schemas.agent_lifecycle_certificate import (
    AgentCertificateResponse,
    CertificateHealthDashboardResponse,
    CertificateHealthStatusEnum,
    CertificateHealthSummaryResponse,
    CertificateStatusEnum,
    CrlSnapshotResponse,
    EmergencyRevocationRequest,
    MintAgentCertificateRequest,
    PreflightVerificationRequest,
    PreflightVerificationResponse,
    RevocationReasonEnum,
    RevocationRecordResponse,
)


class AgentLifecycleCertificateService:
    """Service orchestrating agent digital certificate minting, preflight verification, and CRL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = AgentLifecycleCertificateSuite()
        self._certs_by_id: dict[str, AgentDigitalCertificateSpec] = {}

    def mint_certificate(self, req: MintAgentCertificateRequest) -> AgentCertificateResponse:
        """Mint, cryptographically sign, and register an agent digital certificate."""
        with self._lock:
            spec = self._suite.mint_certificate(
                agent_id=req.agent_id,
                subject_dn=req.subject_dn,
                validity_days=req.validity_days,
                attributes=req.attributes,
            )
            self._certs_by_id[spec.cert_id] = spec

        return self._to_cert_response(spec)

    def get_certificate(self, cert_id: str) -> Optional[AgentCertificateResponse]:
        """Retrieve an issued certificate by ID."""
        with self._lock:
            spec = self._certs_by_id.get(cert_id)
            if spec is None:
                return None
            # Update status if revoked in CRL
            if self._suite.crl_manager.is_cert_id_revoked(spec.cert_id):
                spec = self._with_status(spec, HarnessCertStatusEnum.REVOKED)
            return self._to_cert_response(spec)

    def verify_preflight(self, req: PreflightVerificationRequest) -> PreflightVerificationResponse:
        """Verify an agent digital certificate before granting sandbox invocation."""
        with self._lock:
            spec = self._certs_by_id.get(req.cert_id)

        if spec is None:
            return PreflightVerificationResponse(
                is_allowed=False,
                status=CertificateStatusEnum.REVOKED,
                message=f"Certificate '{req.cert_id}' not found in registry.",
                signature_valid=False,
                not_expired=False,
                not_revoked=False,
                issuer_trusted=False,
            )

        with self._lock:
            res = self._suite.verify_execution(spec, current_time=req.simulated_current_time)

        return PreflightVerificationResponse(
            is_allowed=res.is_allowed,
            status=CertificateStatusEnum(res.status.value),
            message=res.message,
            signature_valid=res.signature_valid,
            not_expired=res.not_expired,
            not_revoked=res.not_revoked,
            issuer_trusted=res.issuer_trusted,
        )

    def emergency_revoke(self, req: EmergencyRevocationRequest) -> Optional[RevocationRecordResponse]:
        """Emergency revoke a certificate and broadcast to CRL."""
        with self._lock:
            spec = self._certs_by_id.get(req.cert_id)
            if spec is None:
                return None

            reason_mapping = {
                RevocationReasonEnum.KEY_COMPROMISE: HarnessRevocationReasonEnum.KEY_COMPROMISE,
                RevocationReasonEnum.CA_COMPROMISE: HarnessRevocationReasonEnum.CA_COMPROMISE,
                RevocationReasonEnum.AFFILIATION_CHANGED: HarnessRevocationReasonEnum.AFFILIATION_CHANGED,
                RevocationReasonEnum.SUPERSEDED: HarnessRevocationReasonEnum.SUPERSEDED,
                RevocationReasonEnum.CESSATION_OF_OPERATION: HarnessRevocationReasonEnum.CESSATION_OF_OPERATION,
                RevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED: HarnessRevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED,
                RevocationReasonEnum.ADMIN_EMERGENCY_SHUTDOWN: HarnessRevocationReasonEnum.ADMIN_EMERGENCY_SHUTDOWN,
            }
            harness_reason = reason_mapping.get(
                req.reason, HarnessRevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED
            )

            record = self._suite.emergency_revoke(
                serial_number=spec.serial_number,
                cert_id=spec.cert_id,
                agent_id=spec.agent_id,
                reason=harness_reason,
                revoked_by=req.revoked_by,
            )

            # Mark updated status in registry
            self._certs_by_id[spec.cert_id] = self._with_status(spec, HarnessCertStatusEnum.REVOKED)

        return RevocationRecordResponse(
            serial_number=record.serial_number,
            cert_id=record.cert_id,
            agent_id=record.agent_id,
            revocation_timestamp=record.revocation_timestamp,
            reason=RevocationReasonEnum(record.reason.value),
            revoked_by=record.revoked_by,
        )

    def get_crl_snapshot(self) -> CrlSnapshotResponse:
        """Retrieve the active CRL snapshot."""
        with self._lock:
            records = self._suite.crl_manager.get_crl_snapshot()

        resp_records = [
            RevocationRecordResponse(
                serial_number=rec.serial_number,
                cert_id=rec.cert_id,
                agent_id=rec.agent_id,
                revocation_timestamp=rec.revocation_timestamp,
                reason=RevocationReasonEnum(rec.reason.value),
                revoked_by=rec.revoked_by,
            )
            for rec in records
        ]
        return CrlSnapshotResponse(total_revoked=len(resp_records), records=resp_records)

    def get_health_dashboard(
        self, current_time: Optional[float] = None
    ) -> CertificateHealthDashboardResponse:
        """Evaluate diagnostic health and expiry status across all certificates."""
        with self._lock:
            all_specs = list(self._certs_by_id.values())

        summaries: list[CertificateHealthSummaryResponse] = []
        healthy = 0
        expiring_soon = 0
        critical_expiry = 0
        expired = 0
        revoked = 0

        for spec in all_specs:
            summary = self._suite.evaluate_health(spec, current_time=current_time)
            status_enum = CertificateHealthStatusEnum(summary.health_status.value)
            summaries.append(
                CertificateHealthSummaryResponse(
                    cert_id=summary.cert_id,
                    agent_id=summary.agent_id,
                    health_status=status_enum,
                    days_until_expiry=summary.days_until_expiry,
                    is_revoked=summary.is_revoked,
                    requires_renewal=summary.requires_renewal,
                )
            )

            if status_enum == CertificateHealthStatusEnum.HEALTHY:
                healthy += 1
            elif status_enum == CertificateHealthStatusEnum.EXPIRING_SOON:
                expiring_soon += 1
            elif status_enum == CertificateHealthStatusEnum.CRITICAL_EXPIRY:
                critical_expiry += 1
            elif status_enum == CertificateHealthStatusEnum.EXPIRED:
                expired += 1
            elif status_enum == CertificateHealthStatusEnum.REVOKED:
                revoked += 1

        return CertificateHealthDashboardResponse(
            total_certificates=len(summaries),
            healthy_count=healthy,
            expiring_soon_count=expiring_soon,
            critical_expiry_count=critical_expiry,
            expired_count=expired,
            revoked_count=revoked,
            summaries=summaries,
        )

    @staticmethod
    def _with_status(
        spec: AgentDigitalCertificateSpec, status: HarnessCertStatusEnum
    ) -> AgentDigitalCertificateSpec:
        """Helper to clone spec with updated status."""
        return AgentDigitalCertificateSpec(
            cert_id=spec.cert_id,
            agent_id=spec.agent_id,
            issuer_dn=spec.issuer_dn,
            subject_dn=spec.subject_dn,
            serial_number=spec.serial_number,
            fingerprint_sha256=spec.fingerprint_sha256,
            not_before=spec.not_before,
            not_after=spec.not_after,
            status=status,
            signature_hex=spec.signature_hex,
            public_key_pem=spec.public_key_pem,
            attributes=spec.attributes,
        )

    @staticmethod
    def _to_cert_response(spec: AgentDigitalCertificateSpec) -> AgentCertificateResponse:
        """Map harness spec to API schema."""
        return AgentCertificateResponse(
            cert_id=spec.cert_id,
            agent_id=spec.agent_id,
            issuer_dn=spec.issuer_dn,
            subject_dn=spec.subject_dn,
            serial_number=spec.serial_number,
            fingerprint_sha256=spec.fingerprint_sha256,
            not_before=spec.not_before,
            not_after=spec.not_after,
            status=CertificateStatusEnum(spec.status.value),
            signature_hex=spec.signature_hex,
            public_key_pem=spec.public_key_pem,
            attributes=spec.attributes,
        )


_SERVICE_INSTANCE: Optional[AgentLifecycleCertificateService] = None
_SERVICE_LOCK = threading.Lock()


def get_agent_lifecycle_certificate_service() -> AgentLifecycleCertificateService:
    """Get the singleton instance of AgentLifecycleCertificateService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = AgentLifecycleCertificateService()
        return _SERVICE_INSTANCE
