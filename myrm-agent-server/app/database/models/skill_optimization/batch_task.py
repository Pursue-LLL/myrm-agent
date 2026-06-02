"""Batch Optimization Task Model

SQLAlchemy model for batch optimization tasks with performance tracking.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BatchOptimizationTask(Base):
    """批量优化任务表

    存储批量优化任务的完整信息，包括任务状态、进度、性能指标等。
    支持任务持久化，服务重启后可恢复任务状态。

    Fields:
        batch_id: Unique batch task identifier
        skill_ids: JSON array of skill IDs to optimize
        status: Task status (pending/running/completed/cancelled)
        priority: Task priority (higher = more urgent)
        max_concurrent: Maximum concurrent tasks
        total_tasks: Total number of tasks
        completed_tasks: Number of completed tasks
        failed_tasks: Number of failed tasks
        cancelled_tasks: Number of cancelled tasks
        total_execution_time: Total execution time in seconds
        total_token_consumption: Total tokens consumed
        estimated_completion_time: Estimated completion timestamp
        created_at: Task creation timestamp
        started_at: Task execution start timestamp
        completed_at: Task completion timestamp
        error_message: Error message if failed
    """

    __tablename__ = "batch_optimization_tasks"

    batch_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_ids: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_execution_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_token_consumption: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    estimated_completion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
