from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.skills.optimization import InMemoryAggregator
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization import (
    ABTestRepository,
    OptimizationRepository,
    QualityRepository,
)
from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.dependencies import (
    get_aggregator,
    get_storage,
)
from app.database.connection import get_db

router = APIRouter()

class DashboardResponse(BaseModel):
    """仪表盘数据"""

    active_optimizations: int
    ab_tests_running: int
    top_skills: list[dict[str, object]]
    bottom_skills: list[dict[str, object]]

class QualityReportResponse(BaseModel):
    """质量报告"""

    skill_id: str
    skill_name: str
    quality_score: dict[str, object]
    recommendation: str

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    """获取仪表盘数据"""
    opt_repo = OptimizationRepository(db)
    ab_repo = ABTestRepository(db)
    quality_repo = QualityRepository(db)

    active_opts = await opt_repo.get_active_optimizations()
    running_tests = await ab_repo.get_running_tests()
    top_skills_data = await quality_repo.get_top_skills(limit=10)
    bottom_skills_data = await quality_repo.get_bottom_skills(limit=10)

    top_skills: list[dict[str, object]] = [{"skill_id": sid, "score": score} for sid, score in top_skills_data]
    bottom_skills: list[dict[str, object]] = [{"skill_id": sid, "score": score} for sid, score in bottom_skills_data]

    return DashboardResponse(
        active_optimizations=len(active_opts),
        ab_tests_running=len(running_tests),
        top_skills=top_skills,
        bottom_skills=bottom_skills,
    )

@router.get("/quality/{skill_id}", response_model=QualityReportResponse)
async def get_skill_quality(skill_id: str, db: AsyncSession = Depends(get_db)) -> QualityReportResponse:
    """获取skill质量报告"""
    quality_repo = QualityRepository(db)

    latest_quality = await quality_repo.get_latest_quality(skill_id)

    if not latest_quality:
        raise HTTPException(status_code=404, detail=f"No quality data found for skill {skill_id}")

    qs_raw = latest_quality.quality_score
    quality_score: dict[str, object] = (
        {str(k): v for k, v in qs_raw.items()} if isinstance(qs_raw, dict) else {"raw": qs_raw}
    )
    overall_raw = quality_score.get("overall_score", 0.0)
    overall_score = float(overall_raw) if isinstance(overall_raw, (int, float)) else 0.0

    if overall_score >= 0.8:
        recommendation = "Excellent quality, no optimization needed"
    elif overall_score >= 0.6:
        recommendation = "Good quality, minor improvements possible"
    else:
        recommendation = "Low quality, optimization recommended"

    return QualityReportResponse(
        skill_id=skill_id,
        skill_name=skill_id,
        quality_score=quality_score,
        recommendation=recommendation,
    )

@router.get("/quality-history/{skill_id}")
async def get_quality_history(
    skill_id: str,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
    days: int = 30,
) -> dict[str, object]:
    """获取skill的质量历史趋势（最近N天）。"""
    history = await storage.get_quality_history(skill_id=skill_id, days=days)

    if not history:
        raise HTTPException(status_code=404, detail=f"No quality history found for skill {skill_id}")

    return {
        "skill_id": skill_id,
        "days": days,
        "history": [
            {
                "timestamp": ts.isoformat(),
                "overall_score": score.overall_score,
                "success_rate": score.success_rate,
                "token_efficiency": score.token_efficiency,
                "execution_time": score.execution_time,
                "user_satisfaction": score.user_satisfaction,
                "call_frequency": score.call_frequency,
            }
            for ts, score in history
        ],
    }

@router.get("/global-metrics")
async def get_global_metrics(
    aggregator: Annotated[InMemoryAggregator, Depends(get_aggregator)],
    time_range_days: int = 30,
) -> dict[str, object]:
    """全局质量指标API，供前端Dashboard展示。"""
    from dataclasses import asdict

    metrics = await aggregator.get_global_metrics(time_range_days=time_range_days)
    result: dict[str, object] = {str(k): v for k, v in asdict(metrics).items()}
    result["calculated_at"] = metrics.calculated_at.isoformat()
    return result

@router.get("/aggregate-by-skill")
async def get_aggregate_by_skill(
    aggregator: Annotated[InMemoryAggregator, Depends(get_aggregator)],
    time_range_days: int = 30,
) -> dict[str, object]:
    """按skill聚合质量指标API，供前端Dashboard展示skill排名。"""
    from dataclasses import asdict

    aggregates = await aggregator.aggregate_by_skill(time_range_days=time_range_days)

    result: list[dict[str, object]] = []
    for agg in aggregates:
        d: dict[str, object] = {str(k): v for k, v in asdict(agg).items()}
        if agg.last_optimization:
            d["last_optimization"] = agg.last_optimization.isoformat()
        if agg.time_range_start:
            d["time_range_start"] = agg.time_range_start.isoformat()
        if agg.time_range_end:
            d["time_range_end"] = agg.time_range_end.isoformat()
        result.append(d)

    return {"aggregates": result, "count": len(result)}

