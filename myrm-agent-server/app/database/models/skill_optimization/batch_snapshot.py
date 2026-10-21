"""Batch Snapshot Model

SQLAlchemy model for the pre-mutation snapshots a skill-modification batch can be undone from.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BatchSnapshot(Base):
    """技能修改批次快照表

    在一批技能修改（skill_manage 等）落盘前，保存被改技能的当前内容快照，
    供撤销该批次时恢复。

    Fields:
        snapshot_id: Unique snapshot identifier
        batch_id: Skill-modification batch ID
        skill_id: Skill ID
        skill_content_before: Skill content before the modification
        skill_version_before: Skill version before the modification
        skill_metadata: Additional metadata captured with the snapshot
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
