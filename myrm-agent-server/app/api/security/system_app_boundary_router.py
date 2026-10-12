"""
[POS] app/api/security/system_app_boundary_router.py
[INPUT] fastapi, app.schemas.system_app_boundary, app.services.security.system_app_boundary_service
[OUTPUT] system_app_boundary_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.system_app_boundary import (
    AppAccessRequestDTO,
    AppAccessVerdictResponseDTO,
    GrantWriteConsentRequestDTO,
    RejectWriteConsentRequestDTO,
    SetScopeRuleRequestDTO,
    SystemAppAuditRecordResponseDTO,
    SystemAppBoundaryMetricsResponseDTO,
    SystemAppScopeRuleResponseDTO,
)
from app.services.security.system_app_boundary_service import (
    SystemAppBoundaryService,
    get_system_app_boundary_service,
)

router = APIRouter(
    prefix="/system-app-boundary",
    tags=["System App Privacy Boundary & Write Consent Gate"],
)


@router.post(
    "/evaluate",
    response_model=AppAccessVerdictResponseDTO,
    summary="Evaluate system app access or mutation attempt",
)
def evaluate_access(
    request: AppAccessRequestDTO,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> AppAccessVerdictResponseDTO:
    """Assert access request against declared container boundaries, tainted context, and write consent policies."""
    return service.evaluate_access(request)


@router.post(
    "/consent/grant",
    response_model=AppAccessVerdictResponseDTO,
    summary="Grant one-time write consent",
)
def grant_write_consent(
    request: GrantWriteConsentRequestDTO,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> AppAccessVerdictResponseDTO:
    """Grant explicit human authorization for a held application write or mutation operation."""
    verdict = service.grant_write_consent(request)
    if verdict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending write request '{request.request_id}' not found for consent",
        )
    return verdict


@router.post(
    "/consent/reject",
    response_model=dict[str, str | bool],
    summary="Reject held write consent request",
)
def reject_write_consent(
    request: RejectWriteConsentRequestDTO,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> dict[str, str | bool]:
    """Reject and dismiss a pending application write request."""
    success = service.reject_write_consent(request)
    return {"request_id": request.request_id, "rejected": success, "reason": request.reason}


@router.get(
    "/consent/pending",
    response_model=list[AppAccessRequestDTO],
    summary="List write requests awaiting human consent",
)
def list_pending_consents(
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> list[AppAccessRequestDTO]:
    """Retrieve all high-risk or unprompted write requests held awaiting human authorization."""
    return service.list_pending_consents()


@router.post(
    "/rules",
    response_model=SystemAppScopeRuleResponseDTO,
    summary="Set or update scoping boundary rule for app",
)
def set_scope_rule(
    request: SetScopeRuleRequestDTO,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> SystemAppScopeRuleResponseDTO:
    """Declare whitelisted container boundaries and unprompted mutation policy for a system application."""
    return service.set_scope_rule(request)


@router.get(
    "/rules/{app_type}",
    response_model=SystemAppScopeRuleResponseDTO,
    summary="Get scoping rule for app",
)
def get_scope_rule(
    app_type: str,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> SystemAppScopeRuleResponseDTO:
    """Fetch declared boundary scope and consent configuration for a system application."""
    return service.get_scope_rule(app_type)


@router.post(
    "/lockdown/{app_type}",
    response_model=SystemAppScopeRuleResponseDTO,
    summary="Place system app under emergency lockdown",
)
def lockdown_app(
    app_type: str,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> SystemAppScopeRuleResponseDTO:
    """Immediately deny all read/write operations against target system application."""
    return service.lockdown_app(app_type)


@router.post(
    "/unlock/{app_type}",
    response_model=SystemAppScopeRuleResponseDTO,
    summary="Release emergency lockdown for system app",
)
def unlock_app(
    app_type: str,
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> SystemAppScopeRuleResponseDTO:
    """Lift emergency lockdown and restore normal boundary checking for system application."""
    return service.unlock_app(app_type)


@router.get(
    "/audit",
    response_model=list[SystemAppAuditRecordResponseDTO],
    summary="Get access audit trail",
)
def get_audit_trail(
    limit: int = Query(default=50, ge=1, le=200),
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> list[SystemAppAuditRecordResponseDTO]:
    """Retrieve chronological audit trail of all evaluated system application access attempts."""
    return service.get_audit_trail(limit=limit)


@router.get(
    "/metrics",
    response_model=SystemAppBoundaryMetricsResponseDTO,
    summary="Get boundary metrics",
)
def get_metrics(
    service: SystemAppBoundaryService = Depends(get_system_app_boundary_service),
) -> SystemAppBoundaryMetricsResponseDTO:
    """Fetch operational counters for privacy boundary evaluations, blocks, and consent grants."""
    return service.get_metrics()
