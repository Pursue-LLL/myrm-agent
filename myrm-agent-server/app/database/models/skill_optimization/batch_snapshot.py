"""Batch Snapshot Model

SQLAlchemy model for batch optimization snapshots (for rollback).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BatchSnapshot(Base):
    """批量优化快照表

    在批量优化开始前，保存所有 skill 的当前状态快照，
    支持一键回滚到优化前的状态。

    Fields:
        snapshot_id: Unique snapshot identifier
        batch_id: Associated batch task ID
        skill_id: Skill ID
        skill_content_before: Skill content before optimization (YAML/JSON)
        skill_version_before: Skill version before optimization
        skill_metadata: Additional metadata (quality scores, etc.)
        created_at: Snapshot creation timestamp
    """

    __tablename__ = "batch_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    skill_content_before: Mapped[str] = mapped_column(Text, nullable=False)
    skill_version_before: Mapped[int] = mapped_column(nullable=False, default=1)

    skill_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
