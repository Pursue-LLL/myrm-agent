"""Skill Quality Aggregation API

Provides REST endpoints for querying skill quality metrics.

Uses new architecture: UniversalAggregator + DataSource Protocol
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.skills.optimization import UniversalAggregator
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization import SQLSkillQualityDataSource
from app.api.dependencies import get_db_session

router = APIRouter(prefix="/skill-quality", tags=["skill-quality"])


def get_aggregator() -> UniversalAggregator:
    """Provide UniversalAggregator with proper session_factory lifecycle."""
    from app.platform_utils import get_session_factory

    data_source = SQLSkillQualityDataSource(get_session_factory())
    return UniversalAggregator(data_source)


@router.get("/metrics/global")
async def get_global_metrics(
    time_range_days: int = 30,
    aggregator: UniversalAggregator = Depends(get_aggregator),
) -> dict[str, object]:
    """Get global skill quality metrics

    Args:
        time_range_days: Time range in days (default: 30)

    Returns:
        Global metrics including total executions, avg quality score, etc.
    """
    metrics = await aggregator.get_global_metrics(time_range_days=time_range_days)

    return {
        "total_executions": metrics.total_executions,
        "total_skills": metrics.total_skills,
        "total_users": metrics.total_users,
        "avg_quality_score": metrics.avg_quality_score,
        "time_range_days": time_range_days,
    }


@router.get("/metrics/skill/{skill_id}")
async def get_skill_metrics(
    skill_id: str,
    time_range_days: int = 30,
    aggregator: UniversalAggregator = Depends(get_aggregator),
) -> dict[str, object]:
    """Get metrics for a specific skill

    Args:
        skill_id: Target skill ID
        time_range_days: Time range in days (default: 30)

    Returns:
        Skill-specific metrics
    """
    results = await aggregator.aggregate_by_skill(skill_id=skill_id, time_range_days=time_range_days)

    if not results:
        raise HTTPException(status_code=404, detail=f"No data found for skill: {skill_id}")

    result = results[0]
    return {
        "skill_id": result.skill_id,
        "sample_count": result.sample_count,
        "total_executions": result.total_executions,
        "avg_quality_score": result.avg_quality_score,
        "avg_success_rate": result.avg_success_rate,
        "avg_token_efficiency": result.avg_token_efficiency,
        "avg_execution_time": result.avg_execution_time,
    }


@router.get("/metrics/user")
async def get_user_metrics(
    time_range_days: int = 30,
    aggregator: UniversalAggregator = Depends(get_aggregator),
) -> dict[str, object]:
    """Get metrics for a specific user

    Args:
        time_range_days: Time range in days (default: 30)

    Returns:
        User-specific metrics
    """
    results = await aggregator.aggregate_by_user(time_range_days=time_range_days)

    if not results:
        raise HTTPException(status_code=404, detail="No data found for user: default")

    result = results[0]
    return {
        "user_id": result.user_id,
        "sample_count": result.sample_count,
        "total_executions": result.total_executions,
        "unique_skills_used": result.unique_skills_used,
        "avg_quality_score": result.avg_quality_score,
    }


@router.get("/metrics/percentiles")
async def get_quality_percentiles(
    aggregator: UniversalAggregator = Depends(get_aggregator),
) -> dict[str, object]:
    """Get quality score percentiles

    Returns:
        Percentile distribution (p50, p90, p95, p99)
    """
    percentiles = await aggregator.get_quality_percentiles()

    if isinstance(percentiles, dict):
        return {str(k): v for k, v in percentiles.items()}
    return {"value": percentiles}


@router.get("/trends/global")
async def get_global_trends(
    time_range_days: int = 30,
    interval_hours: int = 24,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Get global quality trends over time."""
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from app.database.models.skill_optimization.skill_quality_history import SkillQualityHistory

    start_time = datetime.now() - timedelta(days=time_range_days)
    time_bucket = func.strftime("%Y-%m-%d", SkillQualityHistory.recorded_at).label("time_bucket")
    query = (
        select(
            time_bucket,
            func.avg(SkillQualityHistory.overall_score).label("avg_quality"),
            func.avg(SkillQualityHistory.success_rate).label("avg_success_rate"),
            func.avg(SkillQualityHistory.token_efficiency).label("avg_token_efficiency"),
            func.count(SkillQualityHistory.id).label("count"),
        )
        .where(SkillQualityHistory.recorded_at >= start_time)
        .group_by("time_bucket")
        .order_by("time_bucket")
    )

    result = await db.execute(query)
    rows = result.all()

    return {
        "data_points": [
            {
                "timestamp": row.time_bucket,
                "avg_quality_score": float(row.avg_quality) if row.avg_quality else 0.0,
                "avg_success_rate": float(row.avg_success_rate) if row.avg_success_rate else 0.0,
                "avg_token_efficiency": float(row.avg_token_efficiency) if row.avg_token_efficiency else 0.0,
                "execution_count": row.count,
            }
            for row in rows
        ],
        "time_range_days": time_range_days,
        "interval_hours": interval_hours,
    }


@router.get("/trends/skill/{skill_id}")
async def get_skill_trends(
    skill_id: str,
    time_range_days: int = 30,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Get quality trends for a specific skill."""
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from app.database.models.skill_optimization.skill_quality_history import SkillQualityHistory

    start_time = datetime.now() - timedelta(days=time_range_days)
    time_bucket = func.strftime("%Y-%m-%d", SkillQualityHistory.recorded_at).label("time_bucket")
    query = (
        select(
            time_bucket,
            func.avg(SkillQualityHistory.overall_score).label("avg_quality"),
            func.avg(SkillQualityHistory.success_rate).label("avg_success_rate"),
            func.count(SkillQualityHistory.id).label("count"),
        )
        .where(SkillQualityHistory.skill_id == skill_id, SkillQualityHistory.recorded_at >= start_time)
        .group_by("time_bucket")
        .order_by("time_bucket")
    )

    result = await db.execute(query)
    rows = result.all()

    return {
        "skill_id": skill_id,
        "data_points": [
            {
                "timestamp": row.time_bucket,
                "avg_quality_score": float(row.avg_quality) if row.avg_quality else 0.0,
                "avg_success_rate": float(row.avg_success_rate) if row.avg_success_rate else 0.0,
                "execution_count": row.count,
            }
            for row in rows
        ],
        "time_range_days": time_range_days,
    }
