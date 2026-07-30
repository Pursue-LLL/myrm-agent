"""
[INPUT] models.base::Base (POS: ORM model base)
[OUTPUT] AssessmentImportLedger: immutable assessment import dedup ledger
[POS] 评估导入幂等台账。使用 project_id + artifact_version_id 唯一约束防重复导入。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AssessmentImportLedger(Base):
    """Assessment import dedup ledger."""

    __tablename__ = "assessment_import_ledger"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "artifact_version_id",
            name="uq_assessment_import_project_version",
        ),
        Index(
            "ix_assessment_import_project_created_at",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_version_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="reserved",
        server_default="reserved",
    )
    total_milestones: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
