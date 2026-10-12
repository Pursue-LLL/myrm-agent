"""Service layer for NVIDIA SkillSpector Level Skill Supply Chain Security Scanner.

[INPUT]
- myrm_agent_harness.core.security.skill_spector_scanner::*
- app.schemas.skill_spector_scanner::*

[OUTPUT]
- SkillSpectorScannerService, get_skill_spector_scanner_service

[POS]
Service coordinating skill package taint scanning, least-privilege sandbox synthesis, and revocation tracking.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.skill_spector_scanner import (
    NvidiaSkillSpectorScanner,
    SandboxProfile,
    SecurityFinding,
    SkillRevocationRegistry,
    SkillScanReport,
)

from app.schemas.skill_spector_scanner import (
    RevocationListResponse,
    RevocationStatusResponse,
    RevokeSkillRequest,
    SandboxProfileResponse,
    SecurityFindingResponse,
    SkillScanReportResponse,
    SkillScanRequest,
)

logger = logging.getLogger(__name__)


def _to_finding_response(f: SecurityFinding) -> SecurityFindingResponse:
    return SecurityFindingResponse(
        rule_id=f.rule_id,
        category=f.category.value,
        severity=f.severity.value,
        file_name=f.file_name,
        line_number=f.line_number,
        matched_content=f.matched_content,
        description=f.description,
    )


def _to_sandbox_response(s: SandboxProfile) -> SandboxProfileResponse:
    return SandboxProfileResponse(
        network_egress_allowed=s.network_egress_allowed,
        allowed_domains=list(s.allowed_domains),
        read_only_filesystem=s.read_only_filesystem,
        allowed_write_paths=list(s.allowed_write_paths),
        capabilities_dropped=list(s.capabilities_dropped),
    )


def _to_report_response(r: SkillScanReport) -> SkillScanReportResponse:
    return SkillScanReportResponse(
        skill_id=r.skill_id,
        skill_version=r.skill_version,
        safety_rating=r.safety_rating.value,
        is_shield_verified=r.is_shield_verified,
        findings=[_to_finding_response(f) for f in r.findings],
        sandbox_profile=_to_sandbox_response(r.sandbox_profile),
        scanned_at=r.scanned_at,
    )


class SkillSpectorScannerService:
    """Service governing skill supply chain security evaluations and revocation registries."""

    def __init__(
        self,
        scanner: NvidiaSkillSpectorScanner | None = None,
        registry: SkillRevocationRegistry | None = None,
    ) -> None:
        self._scanner: NvidiaSkillSpectorScanner = scanner or NvidiaSkillSpectorScanner()
        self._registry: SkillRevocationRegistry = registry or SkillRevocationRegistry()

    def scan_skill(self, req: SkillScanRequest) -> SkillScanReportResponse:
        """Scan skill files and generate a SkillSpector report."""
        report = self._scanner.scan_skill_package(
            skill_id=req.skill_id,
            skill_version=req.skill_version,
            files=req.files,
            declared_permissions=req.declared_permissions,
        )
        return _to_report_response(report)

    def revoke_skill(self, req: RevokeSkillRequest) -> RevocationStatusResponse:
        """Decommission and revoke a malicious skill from the ecosystem."""
        self._registry.revoke_skill(req.skill_id, req.reason)
        return RevocationStatusResponse(
            skill_id=req.skill_id,
            is_revoked=True,
            reason=req.reason,
        )

    def check_revocation_status(self, skill_id: str) -> RevocationStatusResponse:
        """Check whether a skill ID has been revoked."""
        revoked = self._registry.is_revoked(skill_id)
        reason = self._registry.get_revocation_reason(skill_id)
        return RevocationStatusResponse(
            skill_id=skill_id,
            is_revoked=revoked,
            reason=reason,
        )

    def list_revocations(self) -> RevocationListResponse:
        """List all active skill revocations."""
        revoked = self._registry.list_revoked()
        return RevocationListResponse(
            revoked_skills=revoked,
            total=len(revoked),
        )

    def reset_all(self) -> None:
        """Clear revocation registry (test isolation)."""
        self._registry.clear_all()


_INSTANCE: SkillSpectorScannerService | None = None


def get_skill_spector_scanner_service() -> SkillSpectorScannerService:
    """Return singleton instance of SkillSpectorScannerService."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SkillSpectorScannerService()
    return _INSTANCE
