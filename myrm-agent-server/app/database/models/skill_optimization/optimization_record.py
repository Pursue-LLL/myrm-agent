"""Optimization Record Model

SQLAlchemy model for skill optimization records.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class OptimizationRecord(Base):
    """Skill优化记录表

    存储每次skill优化的完整记录，包括优化前后的质量评分、
    优化内容、执行状态等。
    """

    __tablename__ = "skill_optimization_records"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_type: Mapped[str] = mapped_column(String(50), nullable=False)
    skill_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    baseline_score: Mapped[dict] = mapped_column(JSON, nullable=False)
    optimized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
