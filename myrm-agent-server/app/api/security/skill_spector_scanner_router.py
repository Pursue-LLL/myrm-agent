"""FastAPI router for NVIDIA SkillSpector Level Skill Supply Chain Security Scanner.

[INPUT]
- SkillScanRequest, RevokeSkillRequest payloads.

[OUTPUT]
- SkillScanReportResponse, RevocationStatusResponse, RevocationListResponse.

[POS]
- app.api.security.skill_spector_scanner_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.schemas.skill_spector_scanner import (
    RevocationListResponse,
    RevocationStatusResponse,
    RevokeSkillRequest,
    SkillScanReportResponse,
    SkillScanRequest,
)
from app.services.security.skill_spector_scanner_service import (
    SkillSpectorScannerService,
    get_skill_spector_scanner_service,
)

router = APIRouter(
    prefix="/security/skill-spector",
    tags=["Security - NVIDIA SkillSpector AI Skill Supply Chain Security Scanner"],
)


@router.post("/scan", response_model=SkillScanReportResponse)
async def scan_skill(
    payload: SkillScanRequest,
    service: SkillSpectorScannerService = Depends(get_skill_spector_scanner_service),
) -> SkillScanReportResponse:
    """Scan skill package files for prompt injection, AST taints, and synthesize sandbox profile."""
    return service.scan_skill(payload)


@router.post("/revoke", response_model=RevocationStatusResponse)
async def revoke_skill(
    payload: RevokeSkillRequest,
    service: SkillSpectorScannerService = Depends(get_skill_spector_scanner_service),
) -> RevocationStatusResponse:
    """Decommission and blacklist a compromised or malicious skill ID."""
    return service.revoke_skill(payload)


@router.get("/revocations", response_model=RevocationListResponse)
async def list_revocations(
    service: SkillSpectorScannerService = Depends(get_skill_spector_scanner_service),
) -> RevocationListResponse:
    """List all currently revoked skill packages."""
    return service.list_revocations()


@router.get("/check-status/{skill_id}", response_model=RevocationStatusResponse)
async def check_skill_revocation_status(
    skill_id: str = Path(..., min_length=1, max_length=128, description="Skill identifier"),
    service: SkillSpectorScannerService = Depends(get_skill_spector_scanner_service),
) -> RevocationStatusResponse:
    """Check whether a skill package is flagged as revoked."""
    return service.check_revocation_status(skill_id)
