"""
[POS] app/api/security/skill_health_audit_router.py
[INPUT] fastapi, app.schemas.skill_health_audit, app.services.security.skill_health_audit_service
[OUTPUT] skill_health_audit_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.skill_health_audit import (
    AuditSkillRequestDTO,
    ExportSarifRequestDTO,
    RegisterMaliciousHashRequestDTO,
    SarifExportResponseDTO,
    SkillHealthAuditVerdictDTO,
)
from app.services.security.skill_health_audit_service import (
    SkillHealthAuditService,
    get_skill_health_audit_service,
)

router = APIRouter(
    prefix="/skill-health-audit",
    tags=["Conversational Skill Health Audit & Taint Sentinel"],
)


@router.post(
    "/audit",
    response_model=SkillHealthAuditVerdictDTO,
    summary="Run conversational skill health audit and compute four-row card",
)
def audit_skill(
    request: AuditSkillRequestDTO,
    service: SkillHealthAuditService = Depends(get_skill_health_audit_service),
) -> SkillHealthAuditVerdictDTO:
    """Analyze skill source code, detect undeclared exfiltration sinks, and return score card."""
    return service.audit_skill(request)


@router.post(
    "/export-sarif",
    response_model=SarifExportResponseDTO,
    summary="Export standard SARIF 2.1.0 report for the given skill code",
)
def export_sarif(
    request: ExportSarifRequestDTO,
    service: SkillHealthAuditService = Depends(get_skill_health_audit_service),
) -> SarifExportResponseDTO:
    """Produce OASIS SARIF 2.1.0 standard format for enterprise CI/CD integration."""
    return service.export_sarif(request)


@router.post(
    "/intel/malicious-hashes",
    summary="Register a known malicious hash in local threat intelligence provider",
)
def register_malicious_hash(
    request: RegisterMaliciousHashRequestDTO,
    service: SkillHealthAuditService = Depends(get_skill_health_audit_service),
) -> dict[str, str]:
    """Add a malicious SHA-256 fingerprint into local blocklist feed."""
    service.register_malicious_hash(request)
    return {
        "status": "registered",
        "sha256_hash": request.sha256_hash,
    }
