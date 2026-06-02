"""
[INPUT]
- myrm_agent_harness.runtime.events.skill_events::SkillFailureEvent (POS: Framework-level skill failure event DTOs. They carry runtime evidence for business layers without importing product, GUI, approval, or tenant concepts.)
- myrm_agent_harness.agent.skills.evolution.infra.integration::EvolutionIntegration (POS: Integration helpers for skill evolution system, implements Error-Aware Smart Quarantine (1-Strike/3-Strikes).)
- app.services.skills.evolution_reviews::RuntimeFailureEvidence (POS: 统一的 evolution 审核生命周期服务。以 ApprovalRecord 为唯一事实源，提供幂等落地、回滚与 apply-failed 重试语义。)
- app.services.agent.confidence_approval_flow::ConfidenceApprovalFlow (POS: 基于置信度+客观风控信号的智能审批流。高分且低风险静默自动合并，任何风控红灯即降级人工 Diff Review。)
[OUTPUT]
- handle_skill_failure_event: 将 Harness 运行时技能失败事件转化为幂等的 Server 技能修复/拦截案例。
[POS]
技能免疫业务服务。负责运行时技能失败的业务分类、幂等去重、修复提案生成与审批落地，不向 Harness 或 Control Plane 泄露产品语义。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionRequest,
    EvolutionType,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.infra.integration import (
    EvolutionIntegration,
    get_global_evolution_integration,
)
from myrm_agent_harness.runtime.events import SkillFailureCandidate, SkillFailureEvent

from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_reviews import (
    EvolutionGrowthStatus,
    RuntimeFailureEvidence,
    bump_runtime_failure_review_record,
    create_evolution_review_record,
    find_runtime_failure_review_record,
)

logger = logging.getLogger(__name__)

_ATTRIBUTION_THRESHOLD = 0.75
_CONFIG_PATTERNS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "api key",
    "invalid token",
    "authentication",
    "credentials",
)
_ENVIRONMENT_PATTERNS = (
    "command not found",
    "modulenotfounderror",
    "importerror",
)
_TRANSIENT_PATTERNS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "dns",
    "rate limit",
    "429",
)
_failure_locks: dict[str, asyncio.Lock] = {}


class RuntimeFailureDecision(StrEnum):
    FIX_SKILL = "fix_skill"
    BLOCK_LOCKED = "blocked_locked"
    BLOCK_CONFIGURATION = "blocked_configuration"
    BLOCK_ENVIRONMENT = "blocked_environment"
    BLOCK_TRANSIENT = "blocked_transient"
    BLOCK_ENGINE = "blocked_engine"
    BLOCK_SCREENER = "blocked_screener"
    BLOCK_PROPOSAL = "blocked_proposal"


@dataclass(frozen=True, slots=True)
class FailurePlan:
    candidate: SkillFailureCandidate
    evidence: RuntimeFailureEvidence
    decision: RuntimeFailureDecision
    reason_code: str
    remediation: str


async def handle_skill_failure_event(event: SkillFailureEvent) -> None:
    """Process one Harness skill failure event into the Server skill growth flow."""
    candidate = _select_primary_candidate(event)
    if candidate is None:
        logger.debug("Runtime skill failure skipped: attribution is ambiguous")
        return

    evidence = _build_failure_evidence(event, candidate)
    lock = _failure_locks.setdefault(_idempotency_key(candidate.skill_id, evidence), asyncio.Lock())
    async with lock:
        existing = await find_runtime_failure_review_record(
            skill_id=candidate.skill_id,
            error_signature=evidence.error_signature,
            skill_version=evidence.skill_version,
        )
        if existing is not None:
            await bump_runtime_failure_review_record(
                evolution_id=existing.id,
                last_seen_at=evidence.last_seen_at,
            )
            return

        evolution = get_global_evolution_integration()
        if evolution is None:
            await _create_blocked_case(
                candidate=candidate,
                evidence=evidence,
                skill_record=None,
                decision=RuntimeFailureDecision.BLOCK_ENGINE,
                reason_code="runtime:no_evolution_engine",
                remediation="Configure the background evolution model before runtime skill repair can generate proposals.",
            )
            return

        skill_record = evolution.store.get_skill(candidate.skill_id)
        plan = _build_failure_plan(event, candidate, evidence, skill_record, evolution)
        if plan.decision != RuntimeFailureDecision.FIX_SKILL:
            await _create_blocked_case(
                candidate=candidate,
                evidence=evidence,
                skill_record=skill_record,
                decision=plan.decision,
                reason_code=plan.reason_code,
                remediation=plan.remediation,
            )
            return

        if evolution.screener is not None:
            screen = await evolution.screener.screen_request(
                EvolutionRequest(
                    evolution_type=EvolutionType.FIX,
                    skill_id=candidate.skill_id,
                    reason=_failure_reason(event, evidence),
                )
            )
            if not screen.allowed:
                await _create_blocked_case(
                    candidate=candidate,
                    evidence=evidence,
                    skill_record=skill_record,
                    decision=RuntimeFailureDecision.BLOCK_SCREENER,
                    reason_code="runtime:screener_blocked",
                    remediation=screen.reason,
                )
                return

        if evolution.engine is None:
            await _create_blocked_case(
                candidate=candidate,
                evidence=evidence,
                skill_record=skill_record,
                decision=RuntimeFailureDecision.BLOCK_ENGINE,
                reason_code="runtime:no_evolution_engine",
                remediation="Configure the background evolution model before runtime skill repair can generate proposals.",
            )
            return

        proposal = await evolution.engine.fix_skill(
            candidate.skill_id,
            _failure_reason(event, evidence),
            task_context=_failure_task_context(event, evidence),
            session_id=event.session_id,
        )
        if proposal is None:
            await _create_blocked_case(
                candidate=candidate,
                evidence=evidence,
                skill_record=skill_record,
                decision=RuntimeFailureDecision.BLOCK_PROPOSAL,
                reason_code="runtime:proposal_failed",
                remediation="The evolution engine could not produce a safe repair proposal from this runtime failure.",
            )
            return

        await ConfidenceApprovalFlow().process_evolution(
            proposal,
            runtime_failure=evidence,
            force_manual_review=True,
        )


def _select_primary_candidate(event: SkillFailureEvent) -> SkillFailureCandidate | None:
    candidates = sorted(event.candidates, key=lambda item: item.confidence, reverse=True)
    if not candidates:
        return None
    primary = candidates[0]
    if primary.confidence < _ATTRIBUTION_THRESHOLD:
        return None
    if not primary.skill_id:
        return None
    return primary


def _build_failure_evidence(
    event: SkillFailureEvent,
    candidate: SkillFailureCandidate,
) -> RuntimeFailureEvidence:
    occurred_at = datetime.fromtimestamp(event.occurred_at, UTC).isoformat()
    return RuntimeFailureEvidence(
        tool_name=event.tool_name,
        error_signature=event.error_signature,
        tool_args_hash=event.tool_args_hash or None,
        loop_kind=event.loop_kind,
        skill_version=candidate.version,
        attribution_confidence=candidate.confidence,
        first_seen_at=occurred_at,
        last_seen_at=occurred_at,
        candidate_skill_names=[item.skill_name for item in event.candidates],
    )


def _build_failure_plan(
    event: SkillFailureEvent,
    candidate: SkillFailureCandidate,
    evidence: RuntimeFailureEvidence,
    skill_record: SkillRecord | None,
    evolution: EvolutionIntegration,
) -> FailurePlan:
    if candidate.evolution_locked or (skill_record is not None and skill_record.evolution_locked):
        return FailurePlan(
            candidate=candidate,
            evidence=evidence,
            decision=RuntimeFailureDecision.BLOCK_LOCKED,
            reason_code="runtime:evolution_locked",
            remediation="This skill is locked from automatic evolution. Unlock it before applying runtime repair proposals.",
        )

    if evolution.engine is None:
        return FailurePlan(
            candidate=candidate,
            evidence=evidence,
            decision=RuntimeFailureDecision.BLOCK_ENGINE,
            reason_code="runtime:no_evolution_engine",
            remediation="Configure the background evolution model before runtime skill repair can generate proposals.",
        )

    error_text = event.error_message.lower()
    if _matches(error_text, _CONFIG_PATTERNS):
        return FailurePlan(
            candidate=candidate,
            evidence=evidence,
            decision=RuntimeFailureDecision.BLOCK_CONFIGURATION,
            reason_code="runtime:configuration",
            remediation="Fix the missing or invalid credential/configuration in Settings, then rerun the task.",
        )
    if _matches(error_text, _ENVIRONMENT_PATTERNS):
        return FailurePlan(
            candidate=candidate,
            evidence=evidence,
            decision=RuntimeFailureDecision.BLOCK_ENVIRONMENT,
            reason_code="runtime:environment",
            remediation="Install or expose the missing runtime dependency before changing the skill SOP.",
        )
    if _matches(error_text, _TRANSIENT_PATTERNS):
        return FailurePlan(
            candidate=candidate,
            evidence=evidence,
            decision=RuntimeFailureDecision.BLOCK_TRANSIENT,
            reason_code="runtime:transient",
            remediation="Retry after the external service or network condition recovers. No skill patch is generated for transient failures.",
        )

    return FailurePlan(
        candidate=candidate,
        evidence=evidence,
        decision=RuntimeFailureDecision.FIX_SKILL,
        reason_code="runtime_failure",
        remediation="Review the generated SOP patch against the runtime failure evidence before approving.",
    )


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


async def _create_blocked_case(
    *,
    candidate: SkillFailureCandidate,
    evidence: RuntimeFailureEvidence,
    skill_record: SkillRecord | None,
    decision: RuntimeFailureDecision,
    reason_code: str,
    remediation: str,
) -> None:
    original_content = skill_record.content if skill_record is not None else ""
    skill_name = skill_record.name if skill_record is not None else candidate.skill_name
    skill_path = skill_record.path if skill_record is not None else candidate.storage_path or ""
    await create_evolution_review_record(
        agent_id="default",
        chat_id=None,
        proposal_skill_id=candidate.skill_id,
        skill_name=skill_name,
        skill_path=skill_path,
        evolution_type=EvolutionType.FIX.value,
        reason=f"Runtime skill immune gate: {decision.value}",
        original_content=original_content,
        evolved_content=original_content,
        confidence=0.0,
        test_passed=False,
        task_context=None,
        trajectory=None,
        reason_code=reason_code,
        remediation=remediation,
        runtime_failure=evidence,
        growth_status=(
            EvolutionGrowthStatus.BLOCKED_LOCKED
            if decision == RuntimeFailureDecision.BLOCK_LOCKED
            else EvolutionGrowthStatus.FAILED_SCAN
        ),
        approval_status="REJECTED",
    )


def _failure_reason(event: SkillFailureEvent, evidence: RuntimeFailureEvidence) -> str:
    return (
        "Runtime skill failure detected.\n"
        f"Tool: {event.tool_name}\n"
        f"Error signature: {evidence.error_signature}\n"
        f"Error: {event.error_message}"
    )


def _failure_task_context(
    event: SkillFailureEvent,
    evidence: RuntimeFailureEvidence,
) -> str:
    parts = [
        f"task_intent={event.task_intent or 'unknown'}",
        f"tool={event.tool_name}",
        f"signature={evidence.error_signature}",
        f"args_hash={evidence.tool_args_hash or 'none'}",
        f"attribution_confidence={evidence.attribution_confidence:.2f}",
    ]
    return "\n".join(parts)


def _idempotency_key(skill_id: str, evidence: RuntimeFailureEvidence) -> str:
    return f"{skill_id}:{evidence.skill_version or 'unknown'}:{evidence.error_signature}"
