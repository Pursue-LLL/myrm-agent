"""
[POS] app/services/security/skill_health_audit_service.py
[INPUT] app.schemas.skill_health_audit, myrm_agent_harness.core.security.skill_health_audit
[OUTPUT] SkillHealthAuditService, get_skill_health_audit_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.core.security.skill_health_audit import (
    ConversationalSkillHealthAuditFacade,
    FourRowHealthCard,
    SkillHealthAuditVerdict,
    TaintFlowFinding,
)

from app.schemas.skill_health_audit import (
    AuditSkillRequestDTO,
    ExportSarifRequestDTO,
    FourRowHealthCardDTO,
    RegisterMaliciousHashRequestDTO,
    SarifExportResponseDTO,
    SkillHealthAuditVerdictDTO,
    TaintFlowFindingDTO,
)

logger = logging.getLogger(__name__)


class SkillHealthAuditService:
    """Service orchestrating in-chat skill health audits, taint sentinel analysis, and SARIF exports."""

    def __init__(
        self,
        facade: ConversationalSkillHealthAuditFacade | None = None,
    ) -> None:
        self._facade = facade or ConversationalSkillHealthAuditFacade()

    @staticmethod
    def _to_card_dto(card: FourRowHealthCard) -> FourRowHealthCardDTO:
        return FourRowHealthCardDTO(
            source_credibility=card.source_credibility,
            file_boundary=card.file_boundary,
            network_egress=card.network_egress,
            dangerous_syscalls=card.dangerous_syscalls,
        )

    @staticmethod
    def _to_finding_dto(finding: TaintFlowFinding) -> TaintFlowFindingDTO:
        return TaintFlowFindingDTO(
            source_type=finding.source_type,
            sink_type=finding.sink_type,
            line_number=finding.line_number,
            symbol=finding.symbol,
            is_declared=finding.is_declared,
            severity=finding.severity.value,
            description=finding.description,
        )

    @staticmethod
    def _to_verdict_dto(v: SkillHealthAuditVerdict) -> SkillHealthAuditVerdictDTO:
        return SkillHealthAuditVerdictDTO(
            skill_name=v.skill_name,
            content_sha256=v.content_sha256,
            health_score=v.health_score,
            is_clean=v.is_clean,
            requires_attention=v.requires_attention,
            intel_status=v.intel_status.value,
            plain_language_card=SkillHealthAuditService._to_card_dto(v.plain_language_card),
            taint_findings=[SkillHealthAuditService._to_finding_dto(f) for f in v.taint_findings],
            declared_requests_count=v.declared_requests_count,
            undeclared_sinks_count=v.undeclared_sinks_count,
            actionable_advice=v.actionable_advice,
            disclaimer=v.disclaimer,
            raw_sarif=v.raw_sarif,
        )

    def audit_skill(self, request: AuditSkillRequestDTO) -> SkillHealthAuditVerdictDTO:
        """Run conversational skill health audit and produce score and four-row card."""
        verdict = self._facade.audit_skill(
            skill_name=request.skill_name,
            code=request.code,
            frontmatter_str=request.frontmatter_str,
        )
        logger.info(
            "Audited skill %s: score=%d, clean=%s, undeclared_sinks=%d",
            verdict.skill_name,
            verdict.health_score,
            verdict.is_clean,
            verdict.undeclared_sinks_count,
        )
        return self._to_verdict_dto(verdict)

    def export_sarif(self, request: ExportSarifRequestDTO) -> SarifExportResponseDTO:
        """Export standardized SARIF 2.1.0 report for the given skill code."""
        verdict = self._facade.audit_skill(
            skill_name=request.skill_name,
            code=request.code,
            frontmatter_str=request.frontmatter_str,
        )
        sarif_json = json.dumps(verdict.raw_sarif, indent=2)
        return SarifExportResponseDTO(
            skill_name=request.skill_name,
            sarif_json=sarif_json,
        )

    def register_malicious_hash(self, request: RegisterMaliciousHashRequestDTO) -> bool:
        """Register a known malicious hash in threat intelligence provider."""
        self._facade._intel_provider.register_malicious_hash(request.sha256_hash)
        logger.info("Registered malicious skill hash: %s", request.sha256_hash[:8])
        return True


_global_service: SkillHealthAuditService | None = None


def get_skill_health_audit_service() -> SkillHealthAuditService:
    """Dependency provider for SkillHealthAuditService."""
    global _global_service
    if _global_service is None:
        _global_service = SkillHealthAuditService()
    return _global_service
