"""Shadow Test Sample Model

Records individual execution comparisons between baseline and candidate versions.
Provides evidence for side-by-side quality assessment.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class ShadowSampleModel(Base):
    """影子测试样本记录表"""

    __tablename__ = "skill_shadow_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Execution Info
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    baseline_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Comparison Metrics
    is_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
