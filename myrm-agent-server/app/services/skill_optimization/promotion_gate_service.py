"""Promotion gate adapter for skill optimization (server layer).

[INPUT]
- myrm_agent_harness.agent.skills.evolution.core.promotion_gate::evaluate_promotion_gate
- app.core.skills.store.evolution_store::get_evolution_skill_store
- app.adapters.skill_optimization.sqlalchemy_storage::SQLAlchemyStorage

[OUTPUT]
- evaluate_version_promotion: load versions + eval_cases, run harness gate

[POS]
Business adapter only: no gate logic duplication. Used by ABTestManager promote/auto-promote
and gate-preview HTTP routes.
"""

from __future__ import annotations

import logging
from typing import Any

from myrm_agent_harness.agent.skills.evolution.core.promotion_gate import (
    PromotionVerdictResult,
    evaluate_promotion_gate,
)

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage

logger = logging.getLogger(__name__)


def _load_eval_cases(skill_id: str) -> list[dict[str, Any]]:
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        record = store.get_skill(skill_id)
        if record and record.eval_cases:
            return list(record.eval_cases)
    except Exception as exc:
        logger.warning("Failed to load eval_cases for %s: %s", skill_id, exc)
    return []


async def _resolve_skill_name(skill_id: str) -> str:
    try:
        from app.core.skills.store.service import skills_service

        skill = await skills_service.get_skill(skill_id)
        if skill and skill.name:
            return skill.name
    except Exception as exc:
        logger.debug("Skill name lookup failed for %s: %s", skill_id, exc)
    return skill_id


async def evaluate_version_promotion(
    storage: SQLAlchemyStorage,
    skill_id: str,
    baseline_version: int,
    candidate_version: int,
    *,
    require_eval_cases: bool = True,
) -> PromotionVerdictResult:
    """Run regression gate between two stored skill version snapshots."""
    baseline = await storage.get_skill_version(skill_id, baseline_version)
    candidate = await storage.get_skill_version(skill_id, candidate_version)
    if baseline is None or candidate is None:
        from myrm_agent_harness.agent.skills.evolution.core.promotion_gate import PromotionReasonCode

        return PromotionVerdictResult(
            allowed=False,
            reason_code=PromotionReasonCode.MISSING_CONTENT,
            baseline_pass_rate=0.0,
            candidate_pass_rate=0.0,
            pareto_verdict=None,
            manifest=None,
            message="Baseline or candidate version not found.",
        )

    eval_cases = _load_eval_cases(skill_id)
    skill_name = await _resolve_skill_name(skill_id)

    return evaluate_promotion_gate(
        eval_cases=eval_cases,
        baseline_content=baseline.content,
        candidate_content=candidate.content,
        skill_name=skill_name,
        skill_id=skill_id,
        require_eval_cases=require_eval_cases,
        reasoning="Skill optimization promotion",
    )


def verdict_to_api_dict(verdict: PromotionVerdictResult) -> dict[str, Any]:
    """Serialize gate verdict for REST responses."""
    payload: dict[str, Any] = {
        "allowed": verdict.allowed,
        "reason_code": verdict.reason_code.value,
        "message": verdict.message,
        "baseline_pass_rate": verdict.baseline_pass_rate,
        "candidate_pass_rate": verdict.candidate_pass_rate,
        "pareto_verdict": verdict.pareto_verdict,
    }
    if verdict.manifest is not None:
        payload["manifest"] = verdict.manifest
    return payload
