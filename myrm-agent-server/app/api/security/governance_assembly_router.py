"""API router for Governance Assembly Path Assertion & Zero-Bypass Guard.

[INPUT]
- RecordInvocationRequest, VerifyToolGovernanceRequest, SimulateWorkflowRequest.

[OUTPUT]
- Endpoints for multi-ingress assembly tracing, matrix report auditing,
  and zero-cost offline workflow simulation.

[POS]
- Server API. Mounted under /api/v1/security/governance-assembly.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.schemas.governance_assembly import (
    GovernanceMatrixReportDto,
    RecordInvocationRequest,
    SimulateWorkflowRequest,
    SimulateWorkflowResponse,
    ToolCallAssemblyTraceDto,
    VerifyToolGovernanceRequest,
    VerifyToolGovernanceResponse,
)
from app.services.security.governance_assembly_service import (
    get_governance_assembly_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance-assembly", tags=["governance-assembly"])


@router.post("/invocations", response_model=ToolCallAssemblyTraceDto, status_code=status.HTTP_201_CREATED)
def record_tool_invocation(req: RecordInvocationRequest) -> ToolCallAssemblyTraceDto:
    """Record an observed tool invocation on the execution path."""
    service = get_governance_assembly_service()
    return service.record_invocation(req)


@router.get("/matrix-report", response_model=GovernanceMatrixReportDto)
def get_governance_matrix_report() -> GovernanceMatrixReportDto:
    """Retrieve multi-ingress governance assembly coverage audit report."""
    service = get_governance_assembly_service()
    return service.get_matrix_report()


@router.post("/verify-tool", response_model=VerifyToolGovernanceResponse)
def verify_tool_governance(req: VerifyToolGovernanceRequest) -> VerifyToolGovernanceResponse:
    """Verify whether a tool configuration satisfies mandatory governance middlewares."""
    service = get_governance_assembly_service()
    return service.verify_tool_governance(req)


@router.post("/simulate-workflow", response_model=SimulateWorkflowResponse)
def simulate_workflow(req: SimulateWorkflowRequest) -> SimulateWorkflowResponse:
    """Run an offline recording workflow asserting zero-bypass governance."""
    service = get_governance_assembly_service()
    return service.simulate_workflow(req)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_governance_probe() -> None:
    """Reset accumulated probe traces."""
    service = get_governance_assembly_service()
    service.reset()
