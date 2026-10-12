"""
[POS] app/api/security/policy_conformance_router.py
[INPUT] fastapi, app.schemas.policy_conformance, app.services.security.policy_conformance_service
[OUTPUT] policy_conformance_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.policy_conformance import (
    AuditAgentsRequestDTO,
    AuditAgentsResponseDTO,
    FullConformanceAuditRequestDTO,
    FullConformanceAuditResponseDTO,
    PolicyAuditorMetricsDTO,
    PolicyBaselineDTO,
    RemediateAgentRequestDTO,
    RemediateAgentResponseDTO,
    VerifyRoutingRequestDTO,
    VerifyRoutingResponseDTO,
)
from app.services.security.policy_conformance_service import (
    PolicyConformanceService,
    get_policy_conformance_service,
)

router = APIRouter(
    prefix="/policy-conformance",
    tags=["Agent Policy Conformance & Message Routing Verification"],
)


@router.get(
    "/baseline",
    response_model=PolicyBaselineDTO,
    summary="Get declarative policy baseline",
)
def get_policy_baseline(
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> PolicyBaselineDTO:
    """Fetch active enterprise declarative policy baseline."""
    return service.get_baseline()


@router.put(
    "/baseline",
    response_model=PolicyBaselineDTO,
    summary="Update declarative policy baseline",
)
def update_policy_baseline(
    baseline: PolicyBaselineDTO,
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> PolicyBaselineDTO:
    """Update active enterprise declarative policy baseline."""
    return service.update_baseline(baseline)


@router.post(
    "/audit",
    response_model=AuditAgentsResponseDTO,
    summary="Audit agent runtime configurations",
)
def audit_agents(
    request: AuditAgentsRequestDTO,
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> AuditAgentsResponseDTO:
    """Audit agent runtime configurations against enterprise baseline for drift."""
    return service.audit_agents(request)


@router.post(
    "/remediate",
    response_model=RemediateAgentResponseDTO,
    summary="Remediate agent config to baseline",
)
def remediate_agent(
    request: RemediateAgentRequestDTO,
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> RemediateAgentResponseDTO:
    """Produce compliant configuration snapshot aligned with policy baseline."""
    return service.remediate_agent(request)


@router.post(
    "/verify-routing",
    response_model=VerifyRoutingResponseDTO,
    summary="Verify synthetic message routing accuracy",
)
def verify_message_routing(
    request: VerifyRoutingRequestDTO,
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> VerifyRoutingResponseDTO:
    """Perform zero-cost synthetic message routing assertions against agent rules."""
    return service.verify_routing(request)


@router.post(
    "/full-audit",
    response_model=FullConformanceAuditResponseDTO,
    summary="Execute comprehensive conformance audit and routing verification",
)
def run_full_conformance_audit(
    request: FullConformanceAuditRequestDTO,
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> FullConformanceAuditResponseDTO:
    """Run full policy conformance audit and synthetic message routing verification."""
    return service.run_full_audit(request)


@router.get(
    "/metrics",
    response_model=PolicyAuditorMetricsDTO,
    summary="Get policy auditor operational metrics",
)
def get_metrics(
    service: PolicyConformanceService = Depends(get_policy_conformance_service),
) -> PolicyAuditorMetricsDTO:
    """Fetch cumulative operational metrics for policy audits and routing checks."""
    return service.get_metrics()
