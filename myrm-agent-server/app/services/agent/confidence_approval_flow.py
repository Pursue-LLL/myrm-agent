"""Confidence-based Approval Flow for Skill Evolution.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.types::EvolutionProposal (POS: 标准化进化提案数据结构)
- app.services.skills.evolution_reviews (POS: 统一的 evolution 审核生命周期服务)
[OUTPUT]
- ApprovalResult: 审批流结果（含风控降级原因）
- ConfidenceApprovalFlow: 多信号风控审批流
[POS]
基于置信度+客观风控信号的智能审批流。高分且低风险静默自动合并，任何风控红灯即降级人工 Diff Review。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal

if TYPE_CHECKING:
    from app.services.skills.evolution_reviews import RuntimeFailureEvidence

logger = logging.getLogger(__name__)

DIFF_CHANGE_THRESHOLD = 0.5
EFFECTIVE_RATE_THRESHOLD = 0.5
MIN_APPLIED_FOR_RATE_SIGNAL = 3


@dataclass
class ApprovalResult:
    """Result of confidence-based approval flow."""

    approved: bool
    requires_manual_review: bool
    reason: str
    confidence: float
    risk_signals: list[str] = field(default_factory=list)


class ConfidenceApprovalFlow:
    """Multi-signal risk-aware approval flow for evolved skills."""

    def __init__(self, auto_approve_threshold: float = 0.8):
        self._auto_approve_threshold = auto_approve_threshold

    async def process_evolution(
        self,
        proposal: EvolutionProposal,
        *,
        runtime_failure: "RuntimeFailureEvidence | None" = None,
        force_manual_review: bool = False,
    ) -> ApprovalResult:
        """Process an evolved skill proposal through multi-signal risk assessment.

        Auto-merge requires ALL conditions:
        1. score >= threshold AND is_general (existing LLM signals)
        2. diff change ratio <= 50% (prevents silent large-scale rewrites)
        3. historical effective_rate >= 50% or insufficient data (prevents risky fixes on low-quality skills)
        """
        from app.core.skills.store.evolution_store import get_evolution_skill_store
        from app.services.skills.evolution_reviews import (
            EvolutionApplyError,
            approve_evolution_review_record,
            create_evolution_review_record,
        )

        logger.info(
            "Processing evolution proposal for skill '%s' (score: %.2f)",
            proposal.skill_id,
            proposal.score,
        )

        store = get_evolution_skill_store()
        try:
            skill_record = store.get_skill(proposal.skill_id)
        finally:
            store.close()

        skill_path = skill_record.path if skill_record else ""
        skill_name = skill_record.name if skill_record else proposal.skill_id

        risk_signals = self._evaluate_risk_signals(proposal, skill_record)

        should_auto_approve = (
            proposal.score >= self._auto_approve_threshold
            and getattr(proposal, "is_general", False)
            and len(risk_signals) == 0
            and not force_manual_review
        )
        requires_manual_review = not should_auto_approve

        if risk_signals:
            logger.info(
                "Risk signals triggered for skill '%s': %s",
                proposal.skill_id,
                risk_signals,
            )

        reason = proposal.reasoning
        if proposal.task_context:
            reason += f"\n\n[Task Context]: {proposal.task_context}"

        reason_code: str | None = None
        remediation: str | None = None
        if risk_signals:
            reason_code = "risk:" + ",".join(risk_signals)
            remediation = self._build_remediation(risk_signals)
        elif runtime_failure is not None:
            reason_code = "runtime_failure"
            remediation = (
                "Review the runtime failure evidence and approve only if the "
                "proposed SOP change fixes the repeated failure without widening access."
            )

        review_record = await create_evolution_review_record(
            agent_id=getattr(proposal, "agent_id", None) or "default",
            chat_id=None,
            proposal_skill_id=proposal.skill_id,
            skill_name=skill_name,
            skill_path=skill_path,
            evolution_type=proposal.evolution_type.value,
            reason=reason,
            original_content=proposal.original_content,
            evolved_content=proposal.proposed_content,
            confidence=proposal.score,
            test_passed=proposal.score > 0,
            task_context=proposal.task_context,
            trajectory=proposal.trajectory,
            reason_code=reason_code,
            remediation=remediation,
            runtime_failure=runtime_failure,
        )

        approved = False
        if should_auto_approve:
            try:
                await approve_evolution_review_record(review_record.id, auto_approved=True)
                logger.info(
                    "Auto-merged evolution %s for skill %s",
                    review_record.id,
                    proposal.skill_id,
                )

                from app.services.skills.evolution_events import publish_skill_evolved_event

                publish_skill_evolved_event(
                    skill_name=skill_name,
                    evolution_type=getattr(proposal.evolution_type, "value", proposal.evolution_type),
                    description="Auto-learned skill from background evolution.",
                    evolution_id=review_record.id,
                )

                approved = True
                requires_manual_review = False
            except EvolutionApplyError as exc:
                logger.error("Failed to auto-merge evolution %s: %s", review_record.id, exc)
                requires_manual_review = True

        return ApprovalResult(
            approved=approved,
            requires_manual_review=requires_manual_review,
            reason=reason,
            confidence=proposal.score,
            risk_signals=risk_signals,
        )

    @staticmethod
    def _build_remediation(risk_signals: list[str]) -> str:
        """Generate human-readable remediation text from triggered risk signals."""
        parts: list[str] = []
        for signal in risk_signals:
            if signal.startswith("diff_range:"):
                parts.append("Change exceeds 50% threshold — carefully review the diff to confirm correctness.")
            elif signal.startswith("low_effective_rate:"):
                parts.append("This skill has low historical success rate — verify the improvement direction is correct.")
        return " ".join(parts) if parts else "Review the diff and approve or reject the proposal."

    @staticmethod
    def _evaluate_risk_signals(
        proposal: EvolutionProposal,
        skill_record: object | None,
    ) -> list[str]:
        """Evaluate deterministic risk signals. Returns list of triggered signal names."""
        signals: list[str] = []

        # Signal 1: Diff change ratio — large rewrites should not auto-merge
        original_len = len(proposal.original_content)
        proposed_len = len(proposal.proposed_content)
        if original_len > 0:
            change_ratio = abs(proposed_len - original_len) / original_len
            if change_ratio > DIFF_CHANGE_THRESHOLD:
                signals.append(f"diff_range:{change_ratio:.0%}")

        # Signal 2: Historical effective rate — low-quality skills need human oversight
        if skill_record is not None and hasattr(skill_record, "metrics"):
            metrics = skill_record.metrics
            if metrics.applied_count >= MIN_APPLIED_FOR_RATE_SIGNAL and metrics.effective_rate < EFFECTIVE_RATE_THRESHOLD:
                signals.append(f"low_effective_rate:{metrics.effective_rate:.0%}({metrics.applied_count}runs)")

        return signals
