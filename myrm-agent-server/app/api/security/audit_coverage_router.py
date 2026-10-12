"""API router for Security Audit Explicit Coverage & Replayable Repair Bundles.

[INPUT]
- InitializeAuditSessionRequest, RecordFindingRequest, AttachRepairBundleRequest.

[OUTPUT]
- Endpoints for managing audit sessions, recording challenged findings,
  attaching replayable repair bundles, and fetching explicit coverage reports.

[POS]
- Server API. Mounted under /api/v1/security/audit-coverage.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.core.security.audit_coverage import (
    AuditCoverageError,
    RepairBundleVerificationError,
    UnsupportedFindingError,
)

from app.schemas.audit_coverage import (
    AttachRepairBundleRequest,
    AuditFindingDto,
    ExplicitAuditCoverageReportDto,
    InitializeAuditSessionRequest,
    RecordFindingRequest,
    ReplayableRepairBundleDto,
)
from app.services.security.audit_coverage_service import (
    get_audit_coverage_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-coverage", tags=["audit-coverage"])


@router.post(
    "/session",
    response_model=ExplicitAuditCoverageReportDto,
    status_code=status.HTTP_201_CREATED,
)
def initialize_audit_session(
    req: InitializeAuditSessionRequest,
) -> ExplicitAuditCoverageReportDto:
    """Initialize a new security audit session with declared application model and scopes."""
    service = get_audit_coverage_service()
    return service.initialize_session(req)


@router.post(
    "/findings",
    response_model=AuditFindingDto,
    status_code=status.HTTP_201_CREATED,
)
def record_finding(req: RecordFindingRequest) -> AuditFindingDto:
    """Record an audit finding, asserting application model boundaries and adversarial challenge."""
    service = get_audit_coverage_service()
    try:
        return service.record_finding(req)
    except UnsupportedFindingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/repair-bundles",
    response_model=ReplayableRepairBundleDto,
    status_code=status.HTTP_201_CREATED,
)
def attach_repair_bundle(req: AttachRepairBundleRequest) -> ReplayableRepairBundleDto:
    """Attach and verify a replayable repair bundle to a confirmed audit finding."""
    service = get_audit_coverage_service()
    try:
        return service.attach_repair_bundle(req)
    except (RepairBundleVerificationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except AuditCoverageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/report", response_model=ExplicitAuditCoverageReportDto)
def get_coverage_report() -> ExplicitAuditCoverageReportDto:
    """Retrieve complete audit report disclosing explicit coverage, findings, and repair bundles."""
    service = get_audit_coverage_service()
    return service.get_coverage_report()
