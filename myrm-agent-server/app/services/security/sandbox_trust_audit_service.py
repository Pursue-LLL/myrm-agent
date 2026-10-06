"""Service layer for Sandbox Trust Transparency and Security Isolation Audit Card.

[INPUT]
Logging, standard library datetime, security schemas.

[OUTPUT]
SandboxTrustAuditService, get_sandbox_trust_audit_service.

[POS]
Service layer evaluating network egress violations, filesystem write isolation, and producing sandbox trust cards.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.sandbox_trust_audit import (
    IsolationLevel,
    PermissionBoundaryCard,
    SandboxHealthAuditReport,
    SandboxTrustAuditCardEngine,
    SandboxTrustBadge,
)

from app.schemas.sandbox_trust_audit import (
    GetBoundaryCardRequest,
    GetTrustBadgeRequest,
    PermissionBoundaryCardResponse,
    ProbeCheckItemResponse,
    SandboxHealthAuditReportResponse,
    SandboxHealthAuditRequest,
    SandboxTrustBadgeResponse,
)

logger = logging.getLogger(__name__)


class SandboxTrustAuditService:
    """Coordinates sandbox self-audit scans, trust level badges, and permission boundary cards."""

    def __init__(
        self, engine: SandboxTrustAuditCardEngine | None = None
    ) -> None:
        self.engine = engine or SandboxTrustAuditCardEngine()

    def run_audit(
        self, req: SandboxHealthAuditRequest
    ) -> SandboxHealthAuditReportResponse:
        """Execute sandbox health self-audit probe and evaluate escape prevention."""
        level = IsolationLevel(req.isolation_level.lower())
        report = self.engine.run_environment_audit(
            environment_id=req.environment_id,
            isolation_level=level,
            mounted_paths=req.mounted_paths,
            env_vars=req.env_vars,
            is_root=req.is_root,
            egress_monitored=req.egress_monitored,
        )
        logger.info(
            "Executed sandbox self-audit for environment '%s' [passed=%s, score=%d]",
            report.environment_id,
            report.passed,
            report.score,
        )
        return self._convert_report(report)

    def get_trust_badge(
        self, req: GetTrustBadgeRequest
    ) -> SandboxTrustBadgeResponse:
        """Compute trust badge for visual presentation in client status bars."""
        level = IsolationLevel(req.isolation_level.lower())
        badge = self.engine.generate_badge(
            isolation_level=level,
            audit_score=req.audit_score,
        )
        return self._convert_badge(badge)

    def get_boundary_card(
        self, req: GetBoundaryCardRequest
    ) -> PermissionBoundaryCardResponse:
        """Construct permission hot-boundary card detailing allowed vs protected paths."""
        level = IsolationLevel(req.isolation_level.lower())
        card = self.engine.generate_boundary_card(
            environment_id=req.environment_id,
            isolation_level=level,
            allowed_paths=req.allowed_paths,
        )
        return self._convert_boundary(card)

    @staticmethod
    def _convert_report(
        report: SandboxHealthAuditReport,
    ) -> SandboxHealthAuditReportResponse:
        checks = [
            ProbeCheckItemResponse(
                check_id=c.check_id,
                category=c.category.value,
                description=c.description,
                status=c.status.value,
                details=c.details,
            )
            for c in report.checks
        ]
        return SandboxHealthAuditReportResponse(
            report_id=report.report_id,
            environment_id=report.environment_id,
            isolation_level=report.isolation_level.value,
            checks=checks,
            passed=report.passed,
            score=report.score,
            timestamp=report.timestamp,
        )

    @staticmethod
    def _convert_badge(badge: SandboxTrustBadge) -> SandboxTrustBadgeResponse:
        return SandboxTrustBadgeResponse(
            isolation_level=badge.isolation_level.value,
            trust_grade=badge.trust_grade.value,
            trust_score=badge.trust_score,
            summary=badge.summary,
            badge_label=badge.badge_label,
            color_hex=badge.color_hex,
        )

    @staticmethod
    def _convert_boundary(
        card: PermissionBoundaryCard,
    ) -> PermissionBoundaryCardResponse:
        return PermissionBoundaryCardResponse(
            card_id=card.card_id,
            environment_id=card.environment_id,
            isolation_level=card.isolation_level.value,
            allowed_paths=card.allowed_paths,
            denied_paths=card.denied_paths,
            egress_policy=card.egress_policy,
            active_guards=card.active_guards,
            generated_at=card.generated_at,
        )


_service_instance: SandboxTrustAuditService | None = None


def get_sandbox_trust_audit_service() -> SandboxTrustAuditService:
    """FastAPI dependency provider for SandboxTrustAuditService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SandboxTrustAuditService()
    return _service_instance


def reset_sandbox_trust_audit_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None
