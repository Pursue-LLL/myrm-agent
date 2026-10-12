"""REST API Router for Kernel Continuous Enforcement, Formal Policy Prover,
and Revocation Residue Suite.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException, status
- app.schemas.kernel_continuous_enforcement::(NetworkPolicyRuleSchema, RuntimeHopCheckRequestSchema,
  RuntimeHopCheckResponseSchema, PolicyProposalSubmitRequestSchema, ProverValidationResponseSchema,
  ProposalDetailResponseSchema, RevocationAuditRequestSchema, RevocationResidueReportResponseSchema)
- app.services.security.kernel_continuous_enforcement_service::KernelContinuousEnforcementService

[OUTPUT]
- kernel_continuous_enforcement_router: mounted FastAPI APIRouter

[POS]
REST API interface for 3D continuous enforcement, formal policy prover, and revocation audits.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.kernel_continuous_enforcement import (
    NetworkPolicyRuleSchema,
    PolicyProposalSubmitRequestSchema,
    ProposalDetailResponseSchema,
    ProverValidationResponseSchema,
    RevocationAuditRequestSchema,
    RevocationResidueReportResponseSchema,
    RuntimeHopCheckRequestSchema,
    RuntimeHopCheckResponseSchema,
)
from app.services.security.kernel_continuous_enforcement_service import (
    KernelContinuousEnforcementService,
)

kernel_continuous_enforcement_router = APIRouter(
    prefix="/kernel-continuous-enforcement",
    tags=["Kernel Continuous Enforcement"],
)


def get_enforcement_service() -> KernelContinuousEnforcementService:
    """Dependency provider for KernelContinuousEnforcementService."""
    return KernelContinuousEnforcementService.get_instance()


@kernel_continuous_enforcement_router.post(
    "/evaluate",
    response_model=RuntimeHopCheckResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Evaluate executing binary egress hop against 3D policy",
)
async def evaluate_egress(
    request: RuntimeHopCheckRequestSchema,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> RuntimeHopCheckResponseSchema:
    """Evaluate executing binary egress against active 3D policies."""
    return service.evaluate_egress(request)


@kernel_continuous_enforcement_router.get(
    "/rules",
    response_model=list[NetworkPolicyRuleSchema],
    status_code=status.HTTP_200_OK,
    summary="List all active 3D network policy rules",
)
async def list_rules(
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> list[NetworkPolicyRuleSchema]:
    """Retrieve all active 3D network policy rules."""
    return service.get_active_rules()


@kernel_continuous_enforcement_router.post(
    "/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Add an active 3D network policy rule",
)
async def add_rule(
    rule: NetworkPolicyRuleSchema,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> dict[str, str]:
    """Register an active 3D network policy rule directly."""
    service.add_rule(rule)
    return {"status": "created", "rule_id": rule.rule_id}


@kernel_continuous_enforcement_router.post(
    "/proposals",
    response_model=ProverValidationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Submit agent policy change proposal for formal prover analysis",
)
async def submit_proposal(
    request: PolicyProposalSubmitRequestSchema,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> ProverValidationResponseSchema:
    """Submit a policy change proposal and receive formal proof verification outcome."""
    return service.submit_proposal(request)


@kernel_continuous_enforcement_router.get(
    "/proposals",
    response_model=list[ProposalDetailResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List submitted policy proposals with status and proof details",
)
async def list_proposals(
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> list[ProposalDetailResponseSchema]:
    """List all submitted proposals and their verification status."""
    return service.list_proposals()


@kernel_continuous_enforcement_router.post(
    "/proposals/{proposal_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve proposal and hot-load proposed rules into 3D enforcer",
)
async def approve_proposal(
    proposal_id: str,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> dict[str, str]:
    """Approve a pending policy proposal and hot-load its rules."""
    ok = service.approve_proposal(proposal_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found or not in PENDING status",
        )
    return {"status": "approved", "proposal_id": proposal_id}


@kernel_continuous_enforcement_router.post(
    "/proposals/{proposal_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject proposal",
)
async def reject_proposal(
    proposal_id: str,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> dict[str, str]:
    """Reject a pending policy proposal."""
    ok = service.reject_proposal(proposal_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found or not in PENDING status",
        )
    return {"status": "rejected", "proposal_id": proposal_id}


@kernel_continuous_enforcement_router.post(
    "/revocation/audit",
    response_model=RevocationResidueReportResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Execute post-revocation residue audit for terminated run",
)
async def audit_revocation(
    request: RevocationAuditRequestSchema,
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> RevocationResidueReportResponseSchema:
    """Audit post-revocation environment for surviving artifacts."""
    return service.audit_revocation(request)


@kernel_continuous_enforcement_router.get(
    "/revocation/reports",
    response_model=list[RevocationResidueReportResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="List historical revocation residue audit reports",
)
async def list_residue_reports(
    service: KernelContinuousEnforcementService = Depends(get_enforcement_service),
) -> list[RevocationResidueReportResponseSchema]:
    """Retrieve all historical revocation residue reports."""
    return service.list_residue_reports()
