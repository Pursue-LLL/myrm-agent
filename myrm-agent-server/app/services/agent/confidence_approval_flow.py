"""Confidence-based Approval Flow for Skill Evolution.

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.types::EvolutionProposal, SkillRecord (POS: 标准化进化提案数据结构)
- app.core.skills.curator.service::get_stats_collector, resolve_skill_path (POS: Curator 使用账本 .stats.json)
- app.services.skills.evolution_reviews (POS: 统一的 evolution 审核生命周期服务)
- app.services.skills.evolution_events::publish_skill_evolved_event (POS: SKILL_EVOLVED 前端刷新事件单一出口)
[OUTPUT]
- ApprovalResult: 审批流结果（含风控降级原因）
- ConfidenceApprovalFlow: 多信号风控审批流
[POS]
基于置信度+客观风控信号的智能审批流。高分且低风险静默自动合并，任何风控红灯即降级人工 Diff Review。
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, SkillRecord

if TYPE_CHECKING:
    from app.services.skills.evolution_reviews import RuntimeFailureEvidence

logger = logging.getLogger(__name__)

DIFF_CHANGE_THRESHOLD = 0.5
EFFECTIVE_RATE_THRESHOLD = 0.5
MIN_OBSERVED_FOR_RATE_SIGNAL = 3
_NGRAM_SIZE = 3


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
        2. changed-content ratio <= 50% (prevents silent large-scale rewrites)
        3. historical success rate over observed runs >= 50% or insufficient data (prevents risky fixes on low-quality skills)
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
        skill_record = store.get_skill(proposal.skill_id)

        skill_path = skill_record.path if skill_record else ""
        skill_name = skill_record.name if skill_record else proposal.skill_id

        risk_signals = self._evaluate_risk_signals(proposal, skill_record)

        should_auto_approve = (
            proposal.score >= self._auto_approve_threshold
            and proposal.is_general
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
            agent_id=proposal.agent_id or "default",
            chat_id=None,
            proposal_skill_id=proposal.skill_id,
            skill_name=skill_name,
            skill_path=skill_path,
            evolution_type=proposal.evolution_type.value,
            reason=reason,
            original_content=proposal.original_content,
            evolved_content=proposal.proposed_content,
            confidence=proposal.score,
            test_passed=_scan_outcome(proposal),
            task_context=proposal.task_context,
            trajectory=proposal.trajectory,
            reason_code=reason_code,
            remediation=remediation,
            runtime_failure=runtime_failure,
            eval_cases=proposal.updated_eval_cases,
            security_scan_summary=proposal.security_scan_summary,
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

                from app.services.skills.evolution_events import (
                    publish_skill_evolved_event,
                )

                publish_skill_evolved_event(
                    skill_name=skill_name,
                    evolution_type=proposal.evolution_type.value,
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
        skill_record: SkillRecord | None,
    ) -> list[str]:
        """Evaluate deterministic risk signals. Returns list of triggered signal names."""
        signals: list[str] = []

        # Signal 1: Changed-content ratio — large rewrites should not auto-merge
        if proposal.original_content:
            change_ratio = _changed_content_ratio(proposal.original_content, proposal.proposed_content)
            if change_ratio > DIFF_CHANGE_THRESHOLD:
                signals.append(f"diff_range:{change_ratio:.0%}")

        # Signal 2: Historical success rate — low-quality skills need human oversight
        if skill_record is not None and (low_rate := _low_success_rate_signal(skill_record.name)):
            signals.append(low_rate)

        return signals


def _scan_outcome(proposal: EvolutionProposal) -> bool | None:
    """Whether the security scan of the proposed content found nothing; None when no scan ran.

    A scan rejects only critical findings, so a proposal that reaches review may
    still carry findings: a recorded summary alone does not mean the content is clean.
    """
    summary = proposal.security_scan_summary
    if summary is None:
        return None
    return summary.get("total_findings") == 0


def _ngram_counts(text: str) -> Counter[str]:
    if len(text) < _NGRAM_SIZE:
        return Counter([text]) if text else Counter()
    return Counter(text[i : i + _NGRAM_SIZE] for i in range(len(text) - _NGRAM_SIZE + 1))


def _changed_content_ratio(original: str, proposed: str) -> float:
    """Share of the original's content that was rewritten, removed, or outgrown by additions.

    Compares character n-gram multisets, so a same-length rewrite counts as a
    full rewrite (a plain length comparison reports 0%). N-grams keep the
    measure meaningful for one-line descriptions and for text without
    whitespace such as Chinese, and the comparison is linear time, unlike
    sequence alignment, which degrades badly on repetitive text. ``original``
    must be non-empty.
    """
    original_grams = _ngram_counts(original)
    proposed_grams = _ngram_counts(proposed)
    unchanged = sum((original_grams & proposed_grams).values())
    changed = max(original_grams.total(), proposed_grams.total()) - unchanged
    return changed / original_grams.total()


def _low_success_rate_signal(skill_name: str) -> str | None:
    """Signal text when most observed runs of the skill failed, read from the Curator's usage ledger."""
    from app.core.skills.curator.service import get_stats_collector, resolve_skill_path

    skill_dir = resolve_skill_path(skill_name)
    if skill_dir is None:
        return None
    stats = get_stats_collector().get_stats(skill_dir)
    if stats.observed_count < MIN_OBSERVED_FOR_RATE_SIGNAL or stats.success_rate >= EFFECTIVE_RATE_THRESHOLD:
        return None
    return f"low_effective_rate:{stats.success_rate:.0%}({stats.observed_count}runs)"
