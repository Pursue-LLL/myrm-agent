"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] PendingEvolution, PendingMigration, ExperienceLedgerEvent
[POS] 技能域模型。管理技能进化审批、迁移审批、学习资产事件。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PendingEvolution(Base):
    """@deprecated: 历史遗留表，新数据统一写入 ApprovalRecord。ORM 模型保留仅为避免 DB migration 删表。"""

    __tablename__ = "pending_evolutions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    evolution_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    original_content: Mapped[str] = mapped_column(Text, nullable=False)
    evolved_content: Mapped[str] = mapped_column(Text, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    test_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PendingMigration(Base):
    """待审批的迁移包记录表"""

    __tablename__ = "pending_migrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    migration_type: Mapped[str] = mapped_column(String(50), nullable=False, default="memory_import")
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    applied_result: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperienceLedgerEvent(Base):
    """学习资产事件账本

    只记录会影响长期能力的高价值事实事件。
    """

    __tablename__ = "experience_ledger_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False, default="default", index=True)

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    lineage_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    parent_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    artifact_refs: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    metrics_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
