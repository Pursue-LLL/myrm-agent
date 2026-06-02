"""Quality Repository

CRUD operations for skill quality history and aggregations.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import SkillQualityHistory

logger = logging.getLogger(__name__)


class QualityRepository:
    """质量数据Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_quality_snapshot(self, skill_id: str, quality_score: dict[str, float]) -> SkillQualityHistory:
        """保存质量快照

        Args:
            skill_id: Skill ID
            quality_score: 质量评分数据（包含overall_score等字段）
            user_id: 用户ID（可选，用于用户级聚合）

        Returns:
            SkillQualityHistory: 创建的记录
        """
        snapshot = SkillQualityHistory(
            id=str(uuid4()),
            skill_id=skill_id,
            overall_score=quality_score.get("overall_score", 0.0),
            success_rate=quality_score.get("success_rate", 0.0),
            token_efficiency=quality_score.get("token_efficiency", 0.0),
            execution_time=quality_score.get("execution_time", 0.0),
            user_satisfaction=quality_score.get("user_satisfaction", 0.0),
            call_frequency=quality_score.get("call_frequency", 0.0),
            quality_score=quality_score,
        )
        self.session.add(snapshot)
        await self.session.commit()
        await self.session.refresh(snapshot)
        logger.debug(f"Saved quality snapshot for skill {skill_id} ")
        return snapshot

    async def get_quality_history(
        self,
        skill_id: str,
        days: int = 30,
    ) -> list[SkillQualityHistory]:
        """获取质量历史

        Args:
            skill_id: Skill ID
            days: 查询天数

        Returns:
            list[SkillQualityHistory]: 质量历史记录（按时间升序）
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        result = await self.session.execute(
            select(SkillQualityHistory)
            .where(
                SkillQualityHistory.skill_id == skill_id,
                SkillQualityHistory.recorded_at >= cutoff_time,
            )
            .order_by(SkillQualityHistory.recorded_at)
        )
        return list(result.scalars().all())

    async def get_latest_quality(self, skill_id: str) -> SkillQualityHistory | None:
        """获取最新质量评分

        Args:
            skill_id: Skill ID

        Returns:
            SkillQualityHistory | None: 最新质量记录
        """
        result = await self.session.execute(
            select(SkillQualityHistory)
            .where(SkillQualityHistory.skill_id == skill_id)
            .order_by(desc(SkillQualityHistory.recorded_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_top_skills(self, limit: int = 10) -> list[tuple[str, float]]:
        """获取Top N最佳skill

        Args:
            limit: 返回数量限制

        Returns:
            list[tuple[str, float]]: (skill_id, overall_score)列表
        """
        subquery = (
            select(
                SkillQualityHistory.skill_id,
                func.max(SkillQualityHistory.recorded_at).label("max_time"),
            )
            .group_by(SkillQualityHistory.skill_id)
            .subquery()
        )

        result = await self.session.execute(
            select(SkillQualityHistory.skill_id, SkillQualityHistory.quality_score)
            .join(
                subquery,
                (SkillQualityHistory.skill_id == subquery.c.skill_id) & (SkillQualityHistory.recorded_at == subquery.c.max_time),
            )
            .limit(limit * 2)
        )

        skills_with_scores: list[tuple[str, float]] = []
        for skill_id, quality_score in result:
            if isinstance(quality_score, dict):
                overall_score = quality_score.get("overall_score", 0.0)
                skills_with_scores.append((skill_id, float(overall_score)))

        skills_with_scores.sort(key=lambda x: x[1], reverse=True)
        return skills_with_scores[:limit]

    async def get_bottom_skills(self, limit: int = 10) -> list[tuple[str, float]]:
        """获取Bottom N最差skill

        Args:
            limit: 返回数量限制

        Returns:
            list[tuple[str, float]]: (skill_id, overall_score)列表
        """
        subquery = (
            select(
                SkillQualityHistory.skill_id,
                func.max(SkillQualityHistory.recorded_at).label("max_time"),
            )
            .group_by(SkillQualityHistory.skill_id)
            .subquery()
        )

        result = await self.session.execute(
            select(SkillQualityHistory.skill_id, SkillQualityHistory.quality_score)
            .join(
                subquery,
                (SkillQualityHistory.skill_id == subquery.c.skill_id) & (SkillQualityHistory.recorded_at == subquery.c.max_time),
            )
            .limit(limit * 2)
        )

        skills_with_scores: list[tuple[str, float]] = []
        for skill_id, quality_score in result:
            if isinstance(quality_score, dict):
                overall_score = quality_score.get("overall_score", 0.0)
                skills_with_scores.append((skill_id, float(overall_score)))

        skills_with_scores.sort(key=lambda x: x[1])
        return skills_with_scores[:limit]

    async def get_all_latest_qualities(self) -> dict[str, dict[str, object]]:
        """获取所有skill的最新质量评分

        Returns:
            dict[str, dict]: {skill_id: quality_score}
        """
        subquery = (
            select(
                SkillQualityHistory.skill_id,
                func.max(SkillQualityHistory.recorded_at).label("max_time"),
            )
            .group_by(SkillQualityHistory.skill_id)
            .subquery()
        )

        result = await self.session.execute(
            select(SkillQualityHistory.skill_id, SkillQualityHistory.quality_score).join(
                subquery,
                (SkillQualityHistory.skill_id == subquery.c.skill_id) & (SkillQualityHistory.recorded_at == subquery.c.max_time),
            )
        )

        return {skill_id: quality_score for skill_id, quality_score in result}

    async def delete_old_snapshots(self, days: int = 90) -> int:
        """删除旧的质量快照

        Args:
            days: 保留天数

        Returns:
            int: 删除的记录数
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        result = await self.session.execute(select(SkillQualityHistory).where(SkillQualityHistory.recorded_at < cutoff_time))
        old_snapshots = list(result.scalars().all())

        for snapshot in old_snapshots:
            await self.session.delete(snapshot)

        await self.session.commit()
        count = len(old_snapshots)
        logger.info(f"Deleted {count} old quality snapshots (older than {days} days)")
        return count
