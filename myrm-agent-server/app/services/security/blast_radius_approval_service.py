"""
[POS] app/services/security/blast_radius_approval_service.py
[INPUT] app.schemas.blast_radius_approval, myrm_agent_harness.core.security.blast_radius_approval
[OUTPUT] BlastRadiusApprovalService, get_blast_radius_approval_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.blast_radius_approval import (
    ApprovalSpanGroupPolicy,
    BlastRadiusApprovalFacade,
    DryRunImpactPreview,
    ImpactPreviewTarget,
    LaunchCodeRequirement,
)

from app.schemas.blast_radius_approval import (
    ApprovalSpanGroupPolicyDTO,
    DryRunImpactPreviewDTO,
    EvaluateBatchSpansRequestDTO,
    EvaluateBatchSpansResponseDTO,
    EvaluateCommandApprovalRequestDTO,
    ImpactPreviewTargetDTO,
    LaunchCodeRequirementDTO,
    VerifyLaunchCodeRequestDTO,
    VerifyLaunchCodeResponseDTO,
)

logger = logging.getLogger(__name__)


class BlastRadiusApprovalService:
    """Service mediating blast radius dry-run impact evaluation, launch codes, and span grouping."""

    def __init__(
        self,
        facade: BlastRadiusApprovalFacade | None = None,
    ) -> None:
        self._facade = facade or BlastRadiusApprovalFacade()

    @staticmethod
    def _to_target_dto(t: ImpactPreviewTarget) -> ImpactPreviewTargetDTO:
        return ImpactPreviewTargetDTO(
            path_or_identifier=t.path_or_identifier,
            target_type=t.target_type.value,
            action=t.action,
            estimated_size_bytes=t.estimated_size_bytes,
        )

    @staticmethod
    def _to_preview_dto(p: DryRunImpactPreview | None) -> DryRunImpactPreviewDTO | None:
        if p is None:
            return None
        return DryRunImpactPreviewDTO(
            command=p.command,
            estimated_files_count=p.estimated_files_count,
            estimated_dirs_count=p.estimated_dirs_count,
            targets=[BlastRadiusApprovalService._to_target_dto(t) for t in p.targets],
            is_truncated=p.is_truncated,
            probe_duration_ms=p.probe_duration_ms,
            is_fallback_static=p.is_fallback_static,
            summary=p.summary,
        )

    @staticmethod
    def _to_launch_code_dto(req: LaunchCodeRequirement | None) -> LaunchCodeRequirementDTO | None:
        if req is None:
            return None
        return LaunchCodeRequirementDTO(
            requires_challenge=req.requires_challenge,
            challenge_token=req.challenge_token,
            expected_keyword=req.expected_keyword,
            expires_at=req.expires_at,
            is_used=req.is_used,
            prompt_message=req.prompt_message,
        )

    @staticmethod
    def _to_policy_dto(pol: ApprovalSpanGroupPolicy) -> ApprovalSpanGroupPolicyDTO:
        return ApprovalSpanGroupPolicyDTO(
            span_id=pol.span_id,
            command=pol.command,
            is_destructive=pol.is_destructive,
            never_folded=pol.never_folded,
            impact_preview=BlastRadiusApprovalService._to_preview_dto(pol.impact_preview),
            launch_code=BlastRadiusApprovalService._to_launch_code_dto(pol.launch_code),
            allowed_shortcuts=list(pol.allowed_shortcuts),
        )

    def evaluate_command(
        self, request: EvaluateCommandApprovalRequestDTO
    ) -> ApprovalSpanGroupPolicyDTO:
        """Evaluate dry-run blast radius and launch challenge for a single command."""
        policy = self._facade.evaluate_command_approval(
            command=request.command,
            workspace_dir=request.workspace_dir,
            span_id=request.span_id,
        )
        logger.info(
            "Evaluated command approval for span %s (destructive=%s, launch_code=%s)",
            policy.span_id,
            policy.is_destructive,
            policy.launch_code.requires_challenge if policy.launch_code else False,
        )
        return self._to_policy_dto(policy)

    def evaluate_batch_spans(
        self, request: EvaluateBatchSpansRequestDTO
    ) -> EvaluateBatchSpansResponseDTO:
        """Classify and partition batch spans with never-fold isolation for destructive items."""
        command_tuples = [(item.span_id, item.command) for item in request.commands]
        policies, decision_groups = self._facade.evaluate_batch_spans(
            commands=command_tuples,
            workspace_dir=request.workspace_dir,
        )
        logger.info(
            "Partitioned %d batch spans into %d decision groups",
            len(request.commands),
            len(decision_groups),
        )
        return EvaluateBatchSpansResponseDTO(
            policies=[self._to_policy_dto(p) for p in policies],
            decision_groups=decision_groups,
        )

    def verify_launch_code(
        self, request: VerifyLaunchCodeRequestDTO
    ) -> VerifyLaunchCodeResponseDTO:
        """Verify and consume a typed launch code."""
        is_valid, reason = self._facade.verify_launch_code(
            token=request.token,
            user_input=request.user_input,
        )
        return VerifyLaunchCodeResponseDTO(
            is_valid=is_valid,
            reason=reason,
        )


_global_service: BlastRadiusApprovalService | None = None


def get_blast_radius_approval_service() -> BlastRadiusApprovalService:
    """Dependency provider for BlastRadiusApprovalService."""
    global _global_service
    if _global_service is None:
        _global_service = BlastRadiusApprovalService()
    return _global_service
