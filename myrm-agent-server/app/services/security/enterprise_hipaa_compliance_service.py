"""
[POS] app/services/security/enterprise_hipaa_compliance_service.py
[INPUT] app.schemas.enterprise_hipaa_compliance, myrm_agent_harness.core.security.enterprise_hipaa_compliance
[OUTPUT] EnterpriseHipaaComplianceService, get_enterprise_hipaa_compliance_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.enterprise_hipaa_compliance import (
    BYOCompliantProvider,
    ComplianceExportPackage,
    ComplianceStandard,
    EnterpriseComplianceMetrics,
    EnterpriseHipaaComplianceFacade,
    HipaaAuditChainEntry,
    PhiScreeningResult,
    ProviderComplianceTier,
)

from app.schemas.enterprise_hipaa_compliance import (
    BYOCompliantProviderDTO,
    ComplianceExportPackageDTO,
    EnterpriseComplianceMetricsDTO,
    ExportCompliancePackageRequestDTO,
    HipaaAuditChainEntryDTO,
    PhiScreeningRequestDTO,
    PhiScreeningResponseDTO,
    RecordAuditEventRequestDTO,
    RegisterProviderRequestDTO,
    ValidateProviderEgressRequestDTO,
    ValidateProviderEgressResponseDTO,
    VerifyChainResponseDTO,
)

logger = logging.getLogger(__name__)


class EnterpriseHipaaComplianceService:
    """Service orchestrating HIPAA audit trail, PHI redaction, and BAA egress fences."""

    def __init__(self, facade: EnterpriseHipaaComplianceFacade | None = None) -> None:
        self._facade = facade or EnterpriseHipaaComplianceFacade()

    @staticmethod
    def _to_provider_dto(p: BYOCompliantProvider) -> BYOCompliantProviderDTO:
        return BYOCompliantProviderDTO(
            provider_id=p.provider_id,
            provider_name=p.provider_name,
            base_url=p.base_url,
            tier=p.tier.value,
            baa_agreement_id=p.baa_agreement_id,
            is_zero_training_mandated=p.is_zero_training_mandated,
            permitted_models=list(p.permitted_models),
        )

    @staticmethod
    def _to_ledger_dto(entry: HipaaAuditChainEntry) -> HipaaAuditChainEntryDTO:
        return HipaaAuditChainEntryDTO(
            entry_id=entry.entry_id,
            sequence_index=entry.sequence_index,
            event_type=entry.event_type,
            agent_id=entry.agent_id,
            session_id=entry.session_id,
            timestamp=entry.timestamp,
            action_summary=entry.action_summary,
            phi_detected=entry.phi_detected,
            prev_hash=entry.prev_hash,
            current_hash=entry.current_hash,
        )

    @staticmethod
    def _to_export_dto(pkg: ComplianceExportPackage) -> ComplianceExportPackageDTO:
        return ComplianceExportPackageDTO(
            export_id=pkg.export_id,
            compliance_standard=pkg.compliance_standard.value,
            generated_at=pkg.generated_at,
            total_events=pkg.total_events,
            chain_valid=pkg.chain_valid,
            summary_digest=pkg.summary_digest,
            ledger_entries=[
                EnterpriseHipaaComplianceService._to_ledger_dto(e)
                for e in pkg.ledger_entries
            ],
        )

    @staticmethod
    def _to_phi_dto(scan: PhiScreeningResult) -> PhiScreeningResponseDTO:
        return PhiScreeningResponseDTO(
            is_clean=scan.is_clean,
            detected_phi_categories=list(scan.detected_phi_categories),
            sanitized_content=scan.sanitized_content,
            diagnostic=scan.diagnostic,
        )

    @staticmethod
    def _to_metrics_dto(m: EnterpriseComplianceMetrics) -> EnterpriseComplianceMetricsDTO:
        return EnterpriseComplianceMetricsDTO(
            providers_registered_total=m.providers_registered_total,
            audit_events_recorded_total=m.audit_events_recorded_total,
            phi_violations_blocked_total=m.phi_violations_blocked_total,
            unverified_egress_denied_total=m.unverified_egress_denied_total,
            compliance_exports_generated_total=m.compliance_exports_generated_total,
            zero_training_headers_injected_total=m.zero_training_headers_injected_total,
        )

    def list_providers(self) -> list[BYOCompliantProviderDTO]:
        """List all registered compliant BYO endpoints."""
        providers = self._facade.list_compliant_providers()
        return [self._to_provider_dto(p) for p in providers]

    def get_provider(self, provider_id: str) -> BYOCompliantProviderDTO | None:
        """Fetch compliant provider record by ID."""
        p = self._facade.get_compliant_provider(provider_id)
        if p is None:
            return None
        return self._to_provider_dto(p)

    def register_provider(
        self, request: RegisterProviderRequestDTO
    ) -> BYOCompliantProviderDTO:
        """Register a new Bring-Your-Own compliant provider."""
        tier_map: dict[str, ProviderComplianceTier] = {
            t.value.lower(): t for t in ProviderComplianceTier
        }
        tier = tier_map.get(
            request.tier.lower(), ProviderComplianceTier.VERIFIED_BAA_SIGNED
        )

        provider = BYOCompliantProvider(
            provider_id=request.provider_id,
            provider_name=request.provider_name,
            base_url=request.base_url,
            tier=tier,
            baa_agreement_id=request.baa_agreement_id,
            is_zero_training_mandated=request.is_zero_training_mandated,
            permitted_models=tuple(request.permitted_models),
        )
        self._facade.register_compliant_provider(provider)
        logger.info(
            "Registered compliant provider %s (%s)",
            provider.provider_id,
            provider.tier.value,
        )
        return self._to_provider_dto(provider)

    def record_audit_event(
        self, request: RecordAuditEventRequestDTO
    ) -> HipaaAuditChainEntryDTO:
        """Append an immutable audit entry to the sequential hash ledger."""
        entry = self._facade.record_audit_event(
            event_type=request.event_type,
            agent_id=request.agent_id,
            session_id=request.session_id,
            action_summary=request.action_summary,
            phi_detected=request.phi_detected,
        )
        logger.info(
            "Appended HIPAA audit entry #%d (%s) for session %s",
            entry.sequence_index,
            entry.event_type,
            entry.session_id,
        )
        return self._to_ledger_dto(entry)

    def verify_audit_chain(self) -> VerifyChainResponseDTO:
        """Verify unbroken SHA-256 integrity of the compliance ledger."""
        is_valid, detail = self._facade.verify_audit_integrity()
        return VerifyChainResponseDTO(
            is_valid=is_valid,
            detail=detail,
        )

    def export_compliance_package(
        self, request: ExportCompliancePackageRequestDTO
    ) -> ComplianceExportPackageDTO:
        """Export verifiable compliance proof package with root summary digest."""
        std_map: dict[str, ComplianceStandard] = {
            s.value.lower(): s for s in ComplianceStandard
        }
        std = std_map.get(
            request.compliance_standard.lower(), ComplianceStandard.HIPAA
        )

        pkg = self._facade.export_compliance_package(standard=std)
        logger.info(
            "Exported %s compliance package %s with %d events",
            pkg.compliance_standard.value,
            pkg.export_id,
            pkg.total_events,
        )
        return self._to_export_dto(pkg)

    def screen_phi(self, request: PhiScreeningRequestDTO) -> PhiScreeningResponseDTO:
        """Inspect and pseudonymize Protected Health Information tokens."""
        result = self._facade.screen_phi_content(content=request.content)
        return self._to_phi_dto(result)

    def validate_egress(
        self, request: ValidateProviderEgressRequestDTO
    ) -> ValidateProviderEgressResponseDTO:
        """Evaluate provider against BAA registry and enforce data sovereignty."""
        allowed, headers, diag = self._facade.validate_provider_egress(
            provider_id=request.provider_id,
            content=request.content,
        )
        return ValidateProviderEgressResponseDTO(
            allowed=allowed,
            headers=headers,
            diagnostic=diag,
        )

    def get_metrics(self) -> EnterpriseComplianceMetricsDTO:
        """Retrieve operational telemetry metrics."""
        return self._to_metrics_dto(self._facade.metrics)


_global_service: EnterpriseHipaaComplianceService | None = None


def get_enterprise_hipaa_compliance_service() -> EnterpriseHipaaComplianceService:
    """Dependency provider for EnterpriseHipaaComplianceService."""
    global _global_service
    if _global_service is None:
        _global_service = EnterpriseHipaaComplianceService()
    return _global_service
