"""A/B Test Result Model"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class ABTestResultModel(Base):
    """A/B测试结果表"""

    __tablename__ = "skill_ab_test_results"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    baseline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_score: Mapped[dict] = mapped_column(JSON, nullable=False)
    candidate_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="RUNNING")
    winner: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
