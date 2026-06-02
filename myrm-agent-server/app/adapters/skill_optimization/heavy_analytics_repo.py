"""Heavy Analytics Repository

⚠️ Phase 2.1: 重度分析下沉
将 Harness 层砍掉的复杂聚合逻辑（按天/小时的 OLAP 分析）
下沉到 Server 层，利用 SQLite 的强大 SQL 能力实现。
供前端图表和 Dashboard 使用。
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import SkillQualityHistory

logger = logging.getLogger(__name__)


class HeavyAnalyticsRepository:
    """重度分析 Repository (OLAP in SQLite)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_daily_trend(self, skill_id: str, days: int = 30) -> list[dict[str, object]]:
        """获取按天聚合的质量趋势"""
        cutoff_time = datetime.now() - timedelta(days=days)

        # SQLite date function to extract YYYY-MM-DD
        stmt = (
            select(
                func.date(SkillQualityHistory.recorded_at).label("day"),
                func.avg(SkillQualityHistory.overall_score).label("avg_score"),
                func.avg(SkillQualityHistory.success_rate).label("avg_success"),
                func.count(SkillQualityHistory.id).label("samples"),
            )
            .where(SkillQualityHistory.skill_id == skill_id, SkillQualityHistory.recorded_at >= cutoff_time)
            .group_by(func.date(SkillQualityHistory.recorded_at))
            .order_by("day")
        )

        result = await self.session.execute(stmt)

        trend = []
        for row in result:
            trend.append(
                {
                    "date": row.day,
                    "avg_score": float(row.avg_score) if row.avg_score else 0.0,
                    "avg_success": float(row.avg_success) if row.avg_success else 0.0,
                    "samples": row.samples,
                }
            )

        return trend

    async def get_hourly_activity_pattern(self, skill_id: str, days: int = 30) -> dict[int, int]:
        """获取按小时聚合的活动模式 (0-23)"""
        cutoff_time = datetime.now() - timedelta(days=days)

        # SQLite strftime('%H', ...) returns hour 00-23
        stmt = (
            select(
                func.strftime("%H", SkillQualityHistory.recorded_at).label("hour"),
                func.count(SkillQualityHistory.id).label("sample_count"),
            )
            .where(SkillQualityHistory.skill_id == skill_id, SkillQualityHistory.recorded_at >= cutoff_time)
            .group_by("hour")
        )

        result = await self.session.execute(stmt)

        pattern = {i: 0 for i in range(24)}
        for row in result:
            if row.hour is not None:
                hour_int = int(row.hour)
                pattern[hour_int] = int(row.sample_count)

        return pattern

    async def get_global_summary_stats(self, days: int = 7) -> dict[str, object]:
        """获取全局汇总统计 (所有 Skills)"""
        cutoff_time = datetime.now() - timedelta(days=days)

        stmt = select(
            func.count(func.distinct(SkillQualityHistory.skill_id)).label("active_skills"),
            func.count(SkillQualityHistory.id).label("total_calls"),
            func.avg(SkillQualityHistory.success_rate).label("avg_success_rate"),
            func.avg(SkillQualityHistory.execution_time).label("avg_execution_time"),
        ).where(SkillQualityHistory.recorded_at >= cutoff_time)

        result = await self.session.execute(stmt)
        row = result.first()

        if not row or row.total_calls == 0:
            return {
                "active_skills": 0,
                "total_calls": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": 0.0,
            }

        return {
            "active_skills": row.active_skills,
            "total_calls": row.total_calls,
            "success_rate": float(row.avg_success_rate) if row.avg_success_rate else 0.0,
            # Note: execution_time in DB is efficiency (0-1), we might need raw duration if available
            # For now, returning the efficiency score or a mock duration
            "avg_duration_seconds": 1.0 / (float(row.avg_execution_time) + 0.001) if row.avg_execution_time else 0.0,
        }
