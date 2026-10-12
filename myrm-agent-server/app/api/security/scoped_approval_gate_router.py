"""
[POS] app/api/security/scoped_approval_gate_router.py
[INPUT] fastapi, app.schemas.scoped_approval_gate, app.services.security.scoped_approval_gate_service
[OUTPUT] scoped_approval_gate_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.scoped_approval_gate import (
    ApprovalGrantLeaseDTO,
    AuditLedgerResponseDTO,
    IssueGrantRequestDTO,
    ListActiveGrantsResponseDTO,
    RevokeAllRequestDTO,
    RevokeAllResponseDTO,
    RevokeGrantResponseDTO,
    RiskEvaluationRequestDTO,
    RiskEvaluationResultDTO,
    ScopedApprovalMetricsDTO,
)
from app.services.security.scoped_approval_gate_service import (
    ScopedApprovalGateService,
    get_scoped_approval_gate_service,
)

router = APIRouter(
    prefix="/scoped-approval-gate",
    tags=["Scoped Approval Grants & Risk-Tiered Gate"],
)


@router.post(
    "/grant",
    response_model=ApprovalGrantLeaseDTO,
    summary="Issue scoped approval grant lease",
)
def issue_grant(
    request: IssueGrantRequestDTO,
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> ApprovalGrantLeaseDTO:
    """Issue a scoped authorization lease (once/task/session/24h/always)."""
    return service.issue_grant(request)


@router.post(
    "/evaluate",
    response_model=RiskEvaluationResultDTO,
    summary="Evaluate tool invocation against risk tiers",
)
def evaluate_risk(
    request: RiskEvaluationRequestDTO,
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> RiskEvaluationResultDTO:
    """Evaluate tool invocation against risk tiers and active approval grants."""
    return service.evaluate_risk(request)


@router.post(
    "/revoke/{grant_id}",
    response_model=RevokeGrantResponseDTO,
    summary="Revoke an individual approval lease",
)
def revoke_grant(
    grant_id: str,
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> RevokeGrantResponseDTO:
    """Revoke a specific approval grant by its ID."""
    return service.revoke_grant(grant_id)


@router.post(
    "/revoke-all",
    response_model=RevokeAllResponseDTO,
    summary="Bulk revoke active approval leases",
)
def revoke_all(
    request: RevokeAllRequestDTO,
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> RevokeAllResponseDTO:
    """Revoke all approval leases matching agent or session filters."""
    return service.revoke_all(request)


@router.get(
    "/active-grants",
    response_model=ListActiveGrantsResponseDTO,
    summary="List all active unexpired approval leases",
)
def list_active_grants(
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> ListActiveGrantsResponseDTO:
    """Fetch currently active, non-revoked authorization leases."""
    return service.list_active_grants()


@router.get(
    "/ledger",
    response_model=AuditLedgerResponseDTO,
    summary="Get audit ledger of grant redemptions",
)
def get_audit_ledger(
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> AuditLedgerResponseDTO:
    """Fetch complete historical audit trail of grant redemptions."""
    return service.get_audit_ledger()


@router.get(
    "/metrics",
    response_model=ScopedApprovalMetricsDTO,
    summary="Get operational metrics for scoped approval gates",
)
def get_metrics(
    service: ScopedApprovalGateService = Depends(get_scoped_approval_gate_service),
) -> ScopedApprovalMetricsDTO:
    """Fetch cumulative metrics on evaluations, silent allows, asks, and grants."""
    return service.get_metrics()
