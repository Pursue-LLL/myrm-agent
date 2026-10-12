"""Service for High-Risk Surface CI Gate and Skill Change SecOps Audit.

[INPUT]
- File paths list, Skill content, signing keys, and manifest specifications.

[OUTPUT]
- ScanSurfacesResponse, SkillIntegrityManifestDto, and VerifySkillResponse DTOs.

[POS]
- Server security service. Wraps harness secops_audit subsystem for REST API endpoints.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.secops_audit import (
    HighRiskSurfaceScanner,
    RuntimeSkillIntegrityVerifier,
    SkillIntegrityManifest,
    SkillPermission,
)

from app.schemas.secops_audit import (
    ScanSurfacesRequest,
    ScanSurfacesResponse,
    SignSkillManifestRequest,
    SkillIntegrityManifestDto,
    SurfaceMatchDto,
    VerifySkillRequest,
    VerifySkillResponse,
)


class SecOpsAuditService:
    """Singleton service providing attack surface diff analysis and Skill integrity audits."""

    def __init__(self) -> None:
        self._scanner = HighRiskSurfaceScanner()
        self._verifier = RuntimeSkillIntegrityVerifier()

    def scan_surfaces(self, request: ScanSurfacesRequest) -> ScanSurfacesResponse:
        """Scan paths for public API, Auth, MCP, Migration, and Skill mutations."""
        result = self._scanner.scan_paths(request.paths)
        matches_dto = [
            SurfaceMatchDto(
                path=m.path,
                category=m.category.value,
                suggested_label=m.suggested_label.value,
                reason=m.reason,
            )
            for m in result.matches
        ]
        return ScanSurfacesResponse(
            total_files_scanned=result.total_files_scanned,
            high_risk_detected=result.high_risk_detected,
            requires_multi_party_review=result.requires_multi_party_review,
            applied_labels=list(result.applied_labels),
            matches=matches_dto,
            scanned_at=result.scanned_at,
        )

    def sign_skill_manifest(self, request: SignSkillManifestRequest) -> SkillIntegrityManifestDto:
        """Generate a cryptographically signed integrity manifest for a Skill definition."""
        manifest: SkillIntegrityManifest = self._verifier.sign_manifest(
            skill_name=request.skill_name,
            skill_version=request.skill_version,
            content=request.content,
            secret_key=request.secret_key,
            signed_by=request.signed_by,
        )
        return SkillIntegrityManifestDto(
            skill_name=manifest.skill_name,
            skill_version=manifest.skill_version,
            content_hash=manifest.content_hash,
            declared_permissions=[p.value for p in manifest.declared_permissions],
            signature=manifest.signature,
            signed_by=manifest.signed_by,
            signed_at=manifest.signed_at,
        )

    def verify_skill(self, request: VerifySkillRequest) -> VerifySkillResponse:
        """Audit a skill prior to runtime mounting or merging."""
        harness_manifest: SkillIntegrityManifest | None = None
        if request.manifest:
            harness_manifest = SkillIntegrityManifest(
                skill_name=request.manifest.skill_name,
                skill_version=request.manifest.skill_version,
                content_hash=request.manifest.content_hash,
                declared_permissions=tuple(
                    SkillPermission(p) for p in request.manifest.declared_permissions
                ),
                signature=request.manifest.signature,
                signed_by=request.manifest.signed_by,
                signed_at=request.manifest.signed_at,
            )

        report = self._verifier.verify_skill(
            skill_name=request.skill_name,
            content=request.content,
            manifest=harness_manifest,
            secret_key=request.secret_key,
        )

        return VerifySkillResponse(
            skill_name=report.skill_name,
            is_valid=report.is_valid,
            content_hash=report.content_hash,
            detected_permissions=[p.value for p in report.detected_permissions],
            unapproved_permissions=[p.value for p in report.unapproved_permissions],
            signature_verified=report.signature_verified,
            requires_user_consent=report.requires_user_consent,
            violations=list(report.violations),
        )


_service_lock = threading.Lock()
_global_secops_audit_service: SecOpsAuditService | None = None


def get_secops_audit_service() -> SecOpsAuditService:
    """Retrieve or initialize the global SecOpsAuditService singleton."""
    global _global_secops_audit_service
    if _global_secops_audit_service is None:
        with _service_lock:
            if _global_secops_audit_service is None:
                _global_secops_audit_service = SecOpsAuditService()
    return _global_secops_audit_service
