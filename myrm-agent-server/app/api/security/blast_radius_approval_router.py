"""
[POS] app/api/security/blast_radius_approval_router.py
[INPUT] fastapi, app.schemas.blast_radius_approval, app.services.security.blast_radius_approval_service
[OUTPUT] blast_radius_approval_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.blast_radius_approval import (
    ApprovalSpanGroupPolicyDTO,
    EvaluateBatchSpansRequestDTO,
    EvaluateBatchSpansResponseDTO,
    EvaluateCommandApprovalRequestDTO,
    VerifyLaunchCodeRequestDTO,
    VerifyLaunchCodeResponseDTO,
)
from app.services.security.blast_radius_approval_service import (
    BlastRadiusApprovalService,
    get_blast_radius_approval_service,
)

router = APIRouter(
    prefix="/blast-radius-approval",
    tags=["Blast Radius Dry-Run Impact Preview & Typed Launch Codes"],
)


@router.post(
    "/evaluate",
    response_model=ApprovalSpanGroupPolicyDTO,
    summary="Evaluate impact preview, launch code requirements, and shortcut rules for a command",
)
def evaluate_command_approval(
    request: EvaluateCommandApprovalRequestDTO,
    service: BlastRadiusApprovalService = Depends(get_blast_radius_approval_service),
) -> ApprovalSpanGroupPolicyDTO:
    """Assess command destructiveness, enumerate affected targets via dry-run, and issue challenge code."""
    return service.evaluate_command(request)


@router.post(
    "/batch-evaluate",
    response_model=EvaluateBatchSpansResponseDTO,
    summary="Partition batch spans with never-fold isolation for destructive commands",
)
def evaluate_batch_spans(
    request: EvaluateBatchSpansRequestDTO,
    service: BlastRadiusApprovalService = Depends(get_blast_radius_approval_service),
) -> EvaluateBatchSpansResponseDTO:
    """Group non-destructive commands together while segregating high-risk actions into standalone groups."""
    return service.evaluate_batch_spans(request)


@router.post(
    "/verify-launch-code",
    response_model=VerifyLaunchCodeResponseDTO,
    summary="Verify and invalidate single-use typed launch challenge code",
)
def verify_launch_code(
    request: VerifyLaunchCodeRequestDTO,
    service: BlastRadiusApprovalService = Depends(get_blast_radius_approval_service),
) -> VerifyLaunchCodeResponseDTO:
    """Check typed confirmation token against active challenges and enforce single-use consumption."""
    return service.verify_launch_code(request)
