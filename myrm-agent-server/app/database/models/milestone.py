"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] Milestone: 项目里程碑
[POS] 里程碑域模型。管理项目下的阶段性目标，支持进度追踪和状态流转。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Milestone(Base):
    """里程碑表 — 项目下的阶段性目标"""

    __tablename__ = "project_milestones"
    __table_args__ = (
        Index("ix_milestones_project_status", "project_id", "status"),
        Index("ix_milestones_project_order", "project_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 验收标准（纯文本，Agent 可用于自动判定完成）
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
