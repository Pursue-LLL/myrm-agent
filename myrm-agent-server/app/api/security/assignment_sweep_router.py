"""
[POS] app/api/security/assignment_sweep_router.py
[INPUT] fastapi, app.schemas.assignment_sweep, app.services.security.assignment_sweep_service
[OUTPUT] assignment_sweep_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.assignment_sweep import (
    AssignmentSweepReportDTO,
    AuditDatabaseUrlRequestDTO,
    CheckCleanContentRequestDTO,
    CheckCleanContentResponseDTO,
    DatabaseUrlAuditResultDTO,
    SweepTextRequestDTO,
)
from app.services.security.assignment_sweep_service import (
    AssignmentSweepService,
    get_assignment_sweep_service,
)

router = APIRouter(
    prefix="/assignment-sweep",
    tags=["Quoted-Key Secret Assignment Sweep Hardening"],
)


@router.post(
    "/sweep",
    response_model=AssignmentSweepReportDTO,
    summary="Sweep text, JSON, YAML, or environment files for quoted-key secrets",
)
def sweep_text_content(
    request: SweepTextRequestDTO,
    service: AssignmentSweepService = Depends(get_assignment_sweep_service),
) -> AssignmentSweepReportDTO:
    """Scan content for quoted keys, separator-prefix assignments, and database DSNs."""
    return service.sweep_text(request)


@router.post(
    "/audit-dsn",
    response_model=DatabaseUrlAuditResultDTO | None,
    summary="Audit database connection URL for loopback exemption or leak risk",
)
def audit_database_dsn(
    request: AuditDatabaseUrlRequestDTO,
    service: AssignmentSweepService = Depends(get_assignment_sweep_service),
) -> DatabaseUrlAuditResultDTO | None:
    """Evaluate database URL scheme, loopback status, and default development credentials."""
    return service.audit_database_url(request)


@router.post(
    "/check-clean",
    response_model=CheckCleanContentResponseDTO,
    summary="Fast boolean safety verification for text content",
)
def check_clean_content(
    request: CheckCleanContentRequestDTO,
    service: AssignmentSweepService = Depends(get_assignment_sweep_service),
) -> CheckCleanContentResponseDTO:
    """Perform quick boolean verification ensuring zero unexempted sensitive assignments."""
    return service.check_clean_content(request)
