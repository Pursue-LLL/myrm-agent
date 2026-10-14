"""Skill Optimization Converters

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- myrm_agent_harness.agent.skills.optimization (POS: 框架层领域类型)
- app.database.models.skill_optimization (POS: ORM 行，仅用于类型标注)

[OUTPUT]
- to_optimization_result / to_ab_test_result: ORM 行 -> 框架层领域对象
- to_quality_score / quality_score_to_dict: 质量评分在 JSON 列与 SkillQualityScore 之间互转

[POS]
SQLAlchemyStorage 的无状态转换层（无 I/O）。评分列可能是 None、单个数字或 dict，
统一归一化为 SkillQualityScore，缺失或非数值的维度按 0.0 处理。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.optimization import (
    ABTestResult,
    ABTestStatus,
    OptimizationResult,
    OptimizationStatus,
    SecurityValidationResult,
    SkillQualityScore,
    SkillType,
)

if TYPE_CHECKING:
    from app.database.models.skill_optimization.ab_test_result import ABTestResultModel
    from app.database.models.skill_optimization.optimization_record import OptimizationRecord


def to_optimization_result(record: OptimizationRecord) -> OptimizationResult:
    return OptimizationResult(
        skill_id=record.skill_id,
        skill_type=SkillType(record.skill_type),
        baseline_score=to_quality_score(record.baseline_score),
        optimized_content=record.optimized_content or "",
        security_validation=SecurityValidationResult(passed=True, issues=[]),
        status=OptimizationStatus(record.status),
        started_at=record.started_at,
        completed_at=record.completed_at,
        error=None,
    )


def to_ab_test_result(test: ABTestResultModel) -> ABTestResult:
    return ABTestResult(
        skill_id=test.skill_id,
        baseline_version=test.baseline_version,
        candidate_version=test.candidate_version,
        baseline_score=to_quality_score(test.baseline_score),
        candidate_score=to_quality_score(test.candidate_score),
        sample_size=test.sample_size,
        status=ABTestStatus(test.status),
        started_at=test.started_at,
        completed_at=test.completed_at,
        winner=test.winner,
    )


def to_quality_score(score_raw: object | None) -> SkillQualityScore:
    if score_raw is None:
        return SkillQualityScore(0.0, 0.0, 0.0, 0.0, 0.0)
    if isinstance(score_raw, (int, float)):
        v = float(score_raw)
        return SkillQualityScore(v, v, v, v, v)
    if not isinstance(score_raw, dict):
        return SkillQualityScore(0.0, 0.0, 0.0, 0.0, 0.0)
    d = score_raw

    def gf(key: str, default: float = 0.0) -> float:
        raw = d.get(key, default)
        if isinstance(raw, bool):
            return default
        if isinstance(raw, (int, float)):
            return float(raw)
        return default

    return SkillQualityScore(
        gf("success_rate"),
        gf("token_efficiency"),
        gf("execution_time"),
        gf("user_satisfaction"),
        gf("call_frequency"),
    )


def quality_score_to_dict(score: SkillQualityScore) -> dict[str, float]:
    """将SkillQualityScore转换为dict（序列化用）"""
    return {
        "success_rate": score.success_rate,
        "token_efficiency": score.token_efficiency,
        "execution_time": score.execution_time,
        "user_satisfaction": score.user_satisfaction,
        "call_frequency": score.call_frequency,
        "overall_score": score.overall_score,
    }
