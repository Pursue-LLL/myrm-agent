"""
[POS] app/services/security/assignment_sweep_service.py
[INPUT] app.schemas.assignment_sweep, myrm_agent_harness.core.security.assignment_sweep
[OUTPUT] AssignmentSweepService, get_assignment_sweep_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.assignment_sweep import (
    AssignmentSweepFinding,
    AssignmentSweepReport,
    AssignmentSweepVerdict,
    DatabaseUrlAuditResult,
    QuotedKeySecretAssignmentSweepFacade,
)

from app.schemas.assignment_sweep import (
    AssignmentSweepFindingDTO,
    AssignmentSweepReportDTO,
    AuditDatabaseUrlRequestDTO,
    CheckCleanContentRequestDTO,
    CheckCleanContentResponseDTO,
    DatabaseUrlAuditResultDTO,
    SweepTextRequestDTO,
)

logger = logging.getLogger(__name__)


class AssignmentSweepService:
    """Service mediating quoted-key secret assignment sweeps and database DSN auditing."""

    def __init__(
        self,
        facade: QuotedKeySecretAssignmentSweepFacade | None = None,
    ) -> None:
        self._facade = facade or QuotedKeySecretAssignmentSweepFacade()

    @staticmethod
    def _to_finding_dto(f: AssignmentSweepFinding) -> AssignmentSweepFindingDTO:
        return AssignmentSweepFindingDTO(
            key_name=f.key_name,
            key_family=f.key_family.value,
            raw_matched_line=f.raw_matched_line,
            value_preview=f.value_preview,
            format_kind=f.format_kind.value,
            is_exempt=f.is_exempt,
            exemption_reason=f.exemption_reason,
        )

    @staticmethod
    def _to_report_dto(r: AssignmentSweepReport) -> AssignmentSweepReportDTO:
        return AssignmentSweepReportDTO(
            total_lines_scanned=r.total_lines_scanned,
            findings=[AssignmentSweepService._to_finding_dto(f) for f in r.findings],
            verdict=r.verdict.value,
            active_leaks_count=r.active_leaks_count,
            exempted_count=r.exempted_count,
        )

    @staticmethod
    def _to_dsn_result_dto(d: DatabaseUrlAuditResult | None) -> DatabaseUrlAuditResultDTO | None:
        if d is None:
            return None
        return DatabaseUrlAuditResultDTO(
            raw_url=d.raw_url,
            scheme=d.scheme,
            host=d.host,
            user=d.user,
            is_loopback=d.is_loopback,
            is_default_credential=d.is_default_credential,
            is_exempt=d.is_exempt,
            audit_reason=d.audit_reason,
        )

    def sweep_text(self, request: SweepTextRequestDTO) -> AssignmentSweepReportDTO:
        """Scan source code or configuration text for quoted keys and separator prefix assignments."""
        report = self._facade.sweep_text(request.content)
        logger.info(
            "Completed assignment sweep over %d lines: verdict=%s, active_leaks=%d, exempted=%d",
            report.total_lines_scanned,
            report.verdict.value,
            report.active_leaks_count,
            report.exempted_count,
        )
        return self._to_report_dto(report)

    def audit_database_url(
        self, request: AuditDatabaseUrlRequestDTO
    ) -> DatabaseUrlAuditResultDTO | None:
        """Evaluate database DSN for loopback exemption or high-risk remote exposure."""
        res = self._facade.audit_database_url(request.raw_url)
        return self._to_dsn_result_dto(res)

    def check_clean_content(
        self, request: CheckCleanContentRequestDTO
    ) -> CheckCleanContentResponseDTO:
        """Fast boolean verification whether text is clean of unexempted leaks."""
        report = self._facade.sweep_text(request.content)
        is_clean = report.verdict in {
            AssignmentSweepVerdict.CLEAN,
            AssignmentSweepVerdict.EXEMPTED_LOCAL_DEV,
        }
        return CheckCleanContentResponseDTO(
            is_clean=is_clean,
            verdict=report.verdict.value,
            active_leaks_count=report.active_leaks_count,
        )


_global_service: AssignmentSweepService | None = None


def get_assignment_sweep_service() -> AssignmentSweepService:
    """Dependency provider for AssignmentSweepService."""
    global _global_service
    if _global_service is None:
        _global_service = AssignmentSweepService()
    return _global_service
