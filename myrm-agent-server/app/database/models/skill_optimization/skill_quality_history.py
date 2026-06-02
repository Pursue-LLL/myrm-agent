"""Skill Quality History Model"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class SkillQualityHistory(Base):
    """Skill质量历史表（时间序列）

    支持单机单实例场景的细粒度查询（Agent in Sandbox）。
    """

    __tablename__ = "skill_quality_history"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # User support (for multi-user collaboration within sandbox)

    # Quality score dimensions (denormalized for efficient aggregation)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    token_efficiency: Mapped[float] = mapped_column(Float, nullable=False)
    execution_time: Mapped[float] = mapped_column(Float, nullable=False)
    user_satisfaction: Mapped[float] = mapped_column(Float, nullable=False)
    call_frequency: Mapped[float] = mapped_column(Float, nullable=False)

    # Full quality score JSON (for backward compatibility and detailed analysis)
    quality_score: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Timestamp
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Composite indexes for efficient aggregation queries
    __table_args__ = (
        Index("idx_skill_time", "skill_id", "recorded_at"),
        Index("idx_user_time", "recorded_at"),
        Index("idx_score", "overall_score"),
    )
