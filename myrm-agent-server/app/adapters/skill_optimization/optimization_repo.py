"""Optimization Record Repository

CRUD operations for skill optimization records.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import OptimizationRecord

logger = logging.getLogger(__name__)


class OptimizationRepository:
    """优化记录Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        skill_id: str,
        skill_type: str,
        baseline_score: dict[str, float],
        skill_version: int = 1,
    ) -> OptimizationRecord:
        """创建优化记录

        Args:
            skill_id: Skill ID
            skill_type: Skill类型（PREBUILT/USER/WORKSPACE）
            baseline_score: 基线质量评分
            skill_version: Skill版本号

        Returns:
            OptimizationRecord: 创建的记录
        """
        record = OptimizationRecord(
            id=str(uuid4()),
            skill_id=skill_id,
            skill_type=skill_type,
            baseline_score=baseline_score,
            skill_version=skill_version,
            status="PENDING",
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        logger.info(f"Created optimization record: {record.id} for skill {skill_id}")
        return record

    async def get_by_id(self, record_id: str) -> OptimizationRecord | None:
        """根据ID获取记录"""
        result = await self.session.execute(select(OptimizationRecord).where(OptimizationRecord.id == record_id))
        return result.scalar_one_or_none()

    async def get_by_skill_id(self, skill_id: str, limit: int = 10) -> list[OptimizationRecord]:
        """获取指定skill的优化记录

        Args:
            skill_id: Skill ID
            limit: 返回记录数量限制

        Returns:
            list[OptimizationRecord]: 优化记录列表（按时间倒序）
        """
        result = await self.session.execute(
            select(OptimizationRecord)
            .where(OptimizationRecord.skill_id == skill_id)
            .order_by(desc(OptimizationRecord.started_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 10) -> list[OptimizationRecord]:
        """获取最近的优化记录

        Args:
            limit: 返回记录数量限制

        Returns:
            list[OptimizationRecord]: 优化记录列表（按时间倒序）
        """
        result = await self.session.execute(select(OptimizationRecord).order_by(desc(OptimizationRecord.started_at)).limit(limit))
        return list(result.scalars().all())

    async def get_active_optimizations(self) -> list[OptimizationRecord]:
        """获取进行中的优化记录"""
        result = await self.session.execute(
            select(OptimizationRecord)
            .where(OptimizationRecord.status.in_(["PENDING", "IN_PROGRESS"]))
            .order_by(desc(OptimizationRecord.started_at))
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        record_id: str,
        status: str,
        optimized_content: str | None = None,
        error_message: str | None = None,
    ) -> OptimizationRecord | None:
        """更新优化记录状态

        Args:
            record_id: 记录ID
            status: 新状态（PENDING/IN_PROGRESS/COMPLETED/FAILED）
            optimized_content: 优化后的内容
            error_message: 错误信息

        Returns:
            OptimizationRecord | None: 更新后的记录
        """
        record = await self.get_by_id(record_id)
        if not record:
            return None

        record.status = status
        if optimized_content is not None:
            record.optimized_content = optimized_content
        if error_message is not None:
            record.error_message = error_message

        if status in ["COMPLETED", "FAILED"]:
            from datetime import datetime

            record.completed_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(record)
        logger.info(f"Updated optimization record {record_id} to status: {status}")
        return record

    async def delete(self, record_id: str) -> bool:
        """删除优化记录

        Args:
            record_id: 记录ID

        Returns:
            bool: 是否删除成功
        """
        record = await self.get_by_id(record_id)
        if not record:
            return False

        await self.session.delete(record)
        await self.session.commit()
        logger.info(f"Deleted optimization record: {record_id}")
        return True

    async def delete_old_records(self, days: int = 90) -> int:
        """Delete optimization records whose run started before the retention cutoff."""
        cutoff = datetime.now() - timedelta(days=days)
        result = await self.session.execute(delete(OptimizationRecord).where(OptimizationRecord.started_at < cutoff))
        await self.session.commit()
        if not isinstance(result, CursorResult):
            return 0
        deleted = result.rowcount if result.rowcount is not None else 0
        logger.info("Deleted %s optimization records older than %s days", deleted, days)
        return int(deleted)
