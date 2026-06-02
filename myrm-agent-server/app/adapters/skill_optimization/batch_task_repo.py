"""Batch Task Repository

CRUD operations for batch optimization tasks.
"""

import logging
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization.batch_task import BatchOptimizationTask

logger = logging.getLogger(__name__)


class BatchTaskRepository:
    """批量任务Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        batch_id: str,
        skill_ids: list[str],
        priority: int = 0,
        max_concurrent: int = 3,
        user_id: str | None = None,
    ) -> BatchOptimizationTask:
        """创建批量任务

        Args:
            batch_id: Unique batch identifier
            skill_ids: List of skill IDs to optimize
            priority: Task priority (higher = more urgent)
            max_concurrent: Maximum concurrent tasks
            user_id: User who triggered the batch (optional)

        Returns:
            BatchOptimizationTask: Created batch task record
        """
        task = BatchOptimizationTask(
            batch_id=batch_id,
            user_id=user_id,
            skill_ids={"ids": skill_ids},
            status="pending",
            priority=priority,
            max_concurrent=max_concurrent,
            total_tasks=len(skill_ids),
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        logger.info(f"Created batch task: {batch_id} with {len(skill_ids)} skills")
        return task

    async def get_by_id(self, batch_id: str) -> BatchOptimizationTask | None:
        """根据ID获取批量任务"""
        result = await self.session.execute(select(BatchOptimizationTask).where(BatchOptimizationTask.batch_id == batch_id))
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: str, limit: int = 10) -> list[BatchOptimizationTask]:
        """获取用户的批量任务

        Args:
            user_id: User ID
            limit: Maximum number of records

        Returns:
            list[BatchOptimizationTask]: Batch tasks (ordered by creation time desc)
        """
        result = await self.session.execute(
            select(BatchOptimizationTask).order_by(desc(BatchOptimizationTask.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_tasks(self) -> list[BatchOptimizationTask]:
        """获取进行中的批量任务"""
        result = await self.session.execute(
            select(BatchOptimizationTask)
            .where(BatchOptimizationTask.status.in_(["pending", "running"]))
            .order_by(desc(BatchOptimizationTask.priority), BatchOptimizationTask.created_at)
        )
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 10) -> list[BatchOptimizationTask]:
        """获取最近的批量任务

        Args:
            limit: Maximum number of records

        Returns:
            list[BatchOptimizationTask]: Recent batch tasks
        """
        result = await self.session.execute(
            select(BatchOptimizationTask).order_by(desc(BatchOptimizationTask.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        batch_id: str,
        status: str,
        error_message: str | None = None,
    ) -> BatchOptimizationTask | None:
        """更新批量任务状态

        Args:
            batch_id: Batch ID
            status: New status (pending/running/completed/cancelled)
            error_message: Error message if failed

        Returns:
            BatchOptimizationTask | None: Updated batch task
        """
        task = await self.get_by_id(batch_id)
        if not task:
            return None

        task.status = status
        if error_message is not None:
            task.error_message = error_message

        if status == "running" and task.started_at is None:
            task.started_at = datetime.now()
        elif status in ["completed", "cancelled"]:
            task.completed_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(task)
        logger.info(f"Updated batch task {batch_id} to status: {status}")
        return task

    async def update_progress(
        self,
        batch_id: str,
        completed_tasks: int | None = None,
        failed_tasks: int | None = None,
        cancelled_tasks: int | None = None,
        total_execution_time: float | None = None,
        total_token_consumption: int | None = None,
        estimated_completion_time: datetime | None = None,
    ) -> BatchOptimizationTask | None:
        """更新批量任务进度

        Args:
            batch_id: Batch ID
            completed_tasks: Number of completed tasks
            failed_tasks: Number of failed tasks
            cancelled_tasks: Number of cancelled tasks
            total_execution_time: Total execution time in seconds
            total_token_consumption: Total tokens consumed
            estimated_completion_time: Estimated completion timestamp

        Returns:
            BatchOptimizationTask | None: Updated batch task
        """
        task = await self.get_by_id(batch_id)
        if not task:
            return None

        if completed_tasks is not None:
            task.completed_tasks = completed_tasks
        if failed_tasks is not None:
            task.failed_tasks = failed_tasks
        if cancelled_tasks is not None:
            task.cancelled_tasks = cancelled_tasks
        if total_execution_time is not None:
            task.total_execution_time = total_execution_time
        if total_token_consumption is not None:
            task.total_token_consumption = total_token_consumption
        if estimated_completion_time is not None:
            task.estimated_completion_time = estimated_completion_time

        await self.session.commit()
        await self.session.refresh(task)
        logger.info(f"Updated batch task {batch_id} progress: {task.completed_tasks}/{task.total_tasks}")
        return task

    async def delete(self, batch_id: str) -> bool:
        """删除批量任务

        Args:
            batch_id: Batch ID

        Returns:
            bool: Whether deletion succeeded
        """
        task = await self.get_by_id(batch_id)
        if not task:
            return False

        await self.session.delete(task)
        await self.session.commit()
        logger.info(f"Deleted batch task: {batch_id}")
        return True
