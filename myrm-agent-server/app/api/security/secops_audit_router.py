"""API router for High-Risk Surface CI Gate and Skill Change SecOps Audit.

[INPUT]
- ScanSurfacesRequest, SignSkillManifestRequest, VerifySkillRequest

[OUTPUT]
- JSON endpoints for CI diff surface scanning, skill manifest generation, and skill integrity verification.

[POS]
- Server routing layer under `/api/security/secops`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.schemas.secops_audit import (
    ScanSurfacesRequest,
    ScanSurfacesResponse,
    SignSkillManifestRequest,
    SkillIntegrityManifestDto,
    VerifySkillRequest,
    VerifySkillResponse,
)
from app.services.security.secops_audit_service import get_secops_audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secops", tags=["security-secops-audit"])


@router.post(
    "/scan-surfaces",
    response_model=ScanSurfacesResponse,
    summary="Scan file path changes for high-risk surfaces and generate labels",
)
def scan_surfaces(request: ScanSurfacesRequest) -> ScanSurfacesResponse:
    """Classify modified paths and determine whether multi-party security review is mandated."""
    service = get_secops_audit_service()
    return service.scan_surfaces(request)


@router.post(
    "/skills/sign",
    response_model=SkillIntegrityManifestDto,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a signed cryptographic integrity manifest for a Skill",
)
def sign_skill(request: SignSkillManifestRequest) -> SkillIntegrityManifestDto:
    """Sign a skill content and detect permissions to produce an immutable integrity manifest."""
    service = get_secops_audit_service()
    return service.sign_skill_manifest(request)


@router.post(
    "/skills/verify",
    response_model=VerifySkillResponse,
    summary="Audit and verify a Skill against tampering and unapproved permissions",
)
def verify_skill(request: VerifySkillRequest) -> VerifySkillResponse:
    """Verify hash, signature, and permissions of a Skill prior to mounting or execution."""
    service = get_secops_audit_service()
    return service.verify_skill(request)
