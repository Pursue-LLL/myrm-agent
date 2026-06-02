"""A/B Test Repository

CRUD operations for A/B test results with:
- Atomic sample counting (SQL-level)
- Shadow sample storage with similarity_score
- Retention cleanup (TTL + cap)
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import ABTestResultModel, ShadowSampleModel

logger = logging.getLogger(__name__)


class ABTestRepository:
    """A/B测试Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        skill_id: str,
        baseline_version: int,
        candidate_version: int,
        baseline_score: dict[str, float],
        candidate_score: dict[str, float] | None = None,
    ) -> ABTestResultModel:
        """创建A/B测试记录"""
        result = ABTestResultModel(
            id=str(uuid4()),
            skill_id=skill_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            status="RUNNING",
            sample_size=0,
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        logger.info(f"Created A/B test: {result.id} for skill {skill_id}")
        return result

    async def get_by_id(self, test_id: str) -> ABTestResultModel | None:
        """根据ID获取A/B测试记录"""
        result = await self.session.execute(select(ABTestResultModel).where(ABTestResultModel.id == test_id))
        return result.scalar_one_or_none()

    async def get_running_tests(self) -> list[ABTestResultModel]:
        """获取进行中的A/B测试"""
        result = await self.session.execute(
            select(ABTestResultModel).where(ABTestResultModel.status == "RUNNING").order_by(desc(ABTestResultModel.started_at))
        )
        return list(result.scalars().all())

    async def get_by_skill_id(self, skill_id: str, limit: int = 10) -> list[ABTestResultModel]:
        """获取指定skill的A/B测试记录"""
        result = await self.session.execute(
            select(ABTestResultModel)
            .where(ABTestResultModel.skill_id == skill_id)
            .order_by(desc(ABTestResultModel.started_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        test_id: str,
        status: str,
        winner: str | None = None,
        candidate_score: dict[str, float] | None = None,
        sample_size: int | None = None,
    ) -> ABTestResultModel | None:
        """更新A/B测试状态"""
        test = await self.get_by_id(test_id)
        if not test:
            return None

        test.status = status
        if winner is not None:
            test.winner = winner
        if candidate_score is not None:
            test.candidate_score = candidate_score
        if sample_size is not None:
            test.sample_size = sample_size

        if status != "RUNNING":
            test.completed_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(test)
        logger.info(f"Updated A/B test {test_id} to status: {status}, winner: {winner}")
        return test

    async def atomic_increment_sample_size(self, test_id: str) -> None:
        """原子递增样本计数（SQL级别，并发安全）"""
        await self.session.execute(
            update(ABTestResultModel).where(ABTestResultModel.id == test_id).values(sample_size=ABTestResultModel.sample_size + 1)
        )
        await self.session.commit()

    async def increment_sample_size(self, skill_id: str, increment: int = 1) -> int:
        """Increment sample_size for the latest A/B test row for a skill; returns new total or 0 if none."""
        tests = await self.get_by_skill_id(skill_id, limit=1)
        if not tests:
            return 0
        test_id = tests[0].id
        for _ in range(max(increment, 0)):
            await self.atomic_increment_sample_size(test_id)
        updated = await self.get_by_id(test_id)
        return updated.sample_size if updated else 0

    async def delete(self, test_id: str) -> bool:
        """删除A/B测试记录"""
        test = await self.get_by_id(test_id)
        if not test:
            return False

        await self.session.delete(test)
        await self.session.commit()
        logger.info(f"Deleted A/B test: {test_id}")
        return True

    async def add_shadow_sample(
        self,
        test_id: str,
        skill_id: str,
        inputs: dict[str, object],
        baseline_output: dict[str, object] | None,
        candidate_output: dict[str, object] | None,
        is_match: bool,
        baseline_latency_ms: float,
        candidate_latency_ms: float,
        similarity_score: float | None = None,
        diff_summary: str | None = None,
    ) -> ShadowSampleModel:
        """记录影子测试样本（含 similarity_score）"""
        sample = ShadowSampleModel(
            test_id=test_id,
            skill_id=skill_id,
            inputs=inputs,
            baseline_output=baseline_output,
            candidate_output=candidate_output,
            is_match=is_match,
            similarity_score=similarity_score,
            baseline_latency_ms=baseline_latency_ms,
            candidate_latency_ms=candidate_latency_ms,
            diff_summary=diff_summary,
        )
        self.session.add(sample)
        await self.session.commit()
        return sample

    async def get_samples(self, test_id: str, limit: int = 10) -> list[ShadowSampleModel]:
        """获取指定测试的样本记录"""
        result = await self.session.execute(
            select(ShadowSampleModel)
            .where(ShadowSampleModel.test_id == test_id)
            .order_by(desc(ShadowSampleModel.recorded_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_diverged_samples(self, test_id: str, limit: int = 20) -> list[ShadowSampleModel]:
        """获取分歧样本（is_match=False），用于前端展示"""
        result = await self.session.execute(
            select(ShadowSampleModel)
            .where(ShadowSampleModel.test_id == test_id, ShadowSampleModel.is_match.is_(False))
            .order_by(desc(ShadowSampleModel.recorded_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cleanup_old_samples(self, retention_days: int = 30) -> int:
        """清理已完成测试的旧样本

        Args:
            retention_days: 保留天数

        Returns:
            删除的样本数
        """
        cutoff = datetime.now() - timedelta(days=retention_days)

        completed_tests = await self.session.execute(
            select(ABTestResultModel.id).where(
                ABTestResultModel.status != "RUNNING",
                ABTestResultModel.completed_at < cutoff,
            )
        )
        test_ids = [row[0] for row in completed_tests.all()]

        if not test_ids:
            return 0

        count = 0
        for test_id in test_ids:
            samples = await self.session.execute(select(ShadowSampleModel).where(ShadowSampleModel.test_id == test_id))
            for sample in samples.scalars().all():
                await self.session.delete(sample)
                count += 1

        await self.session.commit()
        logger.info(f"Cleaned up {count} shadow samples from {len(test_ids)} completed tests")
        return count

    async def cap_samples_per_test(self, test_id: str, max_samples: int = 200) -> int:
        """限制每个测试的样本数量，保留最新的，优先保留分歧样本"""
        all_samples = await self.session.execute(
            select(ShadowSampleModel).where(ShadowSampleModel.test_id == test_id).order_by(desc(ShadowSampleModel.recorded_at))
        )
        samples = list(all_samples.scalars().all())

        if len(samples) <= max_samples:
            return 0

        diverged = [s for s in samples if not s.is_match]
        consistent = [s for s in samples if s.is_match]

        keep: list[ShadowSampleModel] = []
        keep.extend(diverged[:max_samples])
        remaining = max_samples - len(keep)
        if remaining > 0:
            keep.extend(consistent[:remaining])

        keep_ids = {s.id for s in keep}
        removed = 0
        for sample in samples:
            if sample.id not in keep_ids:
                await self.session.delete(sample)
                removed += 1

        if removed > 0:
            await self.session.commit()
            logger.info(f"Capped samples for test {test_id}: removed {removed}")

        return removed
