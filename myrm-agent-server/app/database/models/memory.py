"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] ProfileAttribute: 用户画像属性, ProceduralRule: 程序性规则, PendingMemory: 待审批记忆,
SharedContextModel: 共享上下文, SharedContextBindingModel: 共享上下文绑定,
SharedContextWriteProposalModel: 共享上下文写入提案, MemoryOperationEventModel: 记忆操作账本,
MemoryHealthSnapshotModel: 记忆健康快照, MemoryMigrationProvenanceModel: 记忆迁移来源,
MemoryImportDryRunModel: 记忆导入审查会话, MemoryImportBatchModel: 记忆导入批次账本,
MemoryImportItemModel: 记忆导入条目账本, MemoryArchiveRestoreBatchModel: 记忆归档恢复批次账本,
MemoryArchiveRestoreItemModel: 记忆归档恢复条目账本
[POS] 记忆域模型。管理用户画像、程序性规则、待审批记忆和产品层共享上下文。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProfileAttribute(Base):
    """用户画像属性表

    存储从对话中提取的用户特征（偏好、技能、习惯等）。
    每个 (user_id, attribute_key) 组合唯一。
    """

    __tablename__ = "profile_attributes"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)

    attribute_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attribute_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general", index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="extracted")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("attribute_key", name="uq_profile_attribute"),)


class ProceduralRule(Base):
    """程序性记忆规则表

    存储用户的操作偏好规则，如"创建文件时总是使用 UTF-8"。
    """

    __tablename__ = "procedural_rules"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)

    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(String(255), nullable=False, default="general", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PendingMemory(Base):
    """待审批记忆条目表

    Agent 从对话中提取的记忆候选，需要用户确认后才正式存储。
    同时承载冲突裁决记录（is_conflict=True 时生效）。
    """

    __tablename__ = "pending_memories"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    is_conflict: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    conflict_old_memory_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conflict_old_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_importance: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_auto_resolve_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SharedContextModel(Base):
    """产品层共享上下文。

    每个上下文映射到 Harness 的 `shared:<id>` namespace，业务层负责绑定和治理。
    """

    __tablename__ = "shared_contexts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    policy: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    bindings: Mapped[list["SharedContextBindingModel"]] = relationship(
        "SharedContextBindingModel",
        back_populates="context",
        cascade="all, delete-orphan",
    )
    proposals: Mapped[list["SharedContextWriteProposalModel"]] = relationship(
        "SharedContextWriteProposalModel",
        back_populates="context",
        cascade="all, delete-orphan",
    )


class SharedContextBindingModel(Base):
    """共享上下文到业务目标的绑定。"""

    __tablename__ = "shared_context_bindings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    context_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shared_contexts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    context: Mapped["SharedContextModel"] = relationship("SharedContextModel", back_populates="bindings")

    __table_args__ = (UniqueConstraint("context_id", "target_type", "target_id", name="uq_shared_context_binding"),)


class SharedContextWriteProposalModel(Base):
    """共享上下文写入提案。

    Agent 只能提出候选内容，用户批准后才写入对应 shared namespace。
    """

    __tablename__ = "shared_context_write_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    context_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shared_contexts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    context: Mapped["SharedContextModel"] = relationship("SharedContextModel", back_populates="proposals")


class MemoryOperationEventModel(Base):
    """单用户记忆操作账本。

    记录记忆写入、审批、召回影响、导入、健康检查等业务事件，供 GUI 回放、审计和治理使用。
    """

    __tablename__ = "memory_operation_events"
    __table_args__ = (
        Index("ix_memory_operation_events_kind_time", "kind", "occurred_at"),
        Index("ix_memory_operation_events_target", "target_kind", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    memory_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    memory_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_kind: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    influence_refs_json: Mapped[list[dict[str, object]] | None] = mapped_column("influence_refs", JSON, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)


class MemoryHealthSnapshotModel(Base):
    """缓存的记忆健康快照，避免设置页高频触发昂贵检查。"""

    __tablename__ = "memory_health_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dimensions_json: Mapped[dict[str, float]] = mapped_column("dimensions", JSON, nullable=False, default=dict)
    suggestions_json: Mapped[list[str]] = mapped_column("suggestions", JSON, nullable=False, default=list)
    has_graph: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guardian_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seconds_until_next: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)


class MemoryMigrationProvenanceModel(Base):
    """外部记忆导入来源账本。"""

    __tablename__ = "memory_migration_provenance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)


class MemoryImportDryRunModel(Base):
    """记忆导入审查会话。"""

    __tablename__ = "memory_import_dry_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_data_json: Mapped[dict[str, object]] = mapped_column("normalized_data", JSON, nullable=False, default=dict)
    summary_json: Mapped[dict[str, object]] = mapped_column("summary", JSON, nullable=False, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column("warnings", JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)


class MemoryImportBatchModel(Base):
    """记忆导入确认批次账本。

    只保存回滚和审计所需的内容盲摘要，不保存导入正文。
    """

    __tablename__ = "memory_import_batches"
    __table_args__ = (
        Index("ix_memory_import_batches_dry_run", "dry_run_id"),
        Index("ix_memory_import_batches_status_time", "status", "confirmed_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dry_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diagnostic_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    diagnostic_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    diagnostic_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollback_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rolled_back_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)

    items: Mapped[list["MemoryImportItemModel"]] = relationship(
        "MemoryImportItemModel",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class MemoryImportItemModel(Base):
    """记忆导入条目账本。

    用显式状态机和导入前后指纹支撑精准回滚与画像并发冲突检测。
    """

    __tablename__ = "memory_import_items"
    __table_args__ = (
        Index("ix_memory_import_items_batch_type", "batch_id", "memory_type"),
        Index("ix_memory_import_items_batch_status", "batch_id", "status"),
        Index("ix_memory_import_items_profile_key", "profile_key"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("memory_import_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    memory_ids_json: Mapped[list[str]] = mapped_column("memory_ids", JSON, nullable=False, default=list)
    profile_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_imported_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_previous_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_imported_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_previous_value_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile_imported_value_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollback_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rollback_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)

    batch: Mapped["MemoryImportBatchModel"] = relationship("MemoryImportBatchModel", back_populates="items")


class MemoryArchiveRestoreBatchModel(Base):
    """记忆归档恢复批次账本。

    保存归档恢复的内容盲摘要和回滚状态，支撑 Local/Tauri/Sandbox 单用户恢复闭环。
    """

    __tablename__ = "memory_archive_restore_batches"
    __table_args__ = (
        Index("ix_memory_archive_restore_batches_status_time", "status", "confirmed_at"),
        Index("ix_memory_archive_restore_batches_rollback_status", "rollback_status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="myrm_archive", index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    restored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollback_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rolled_back_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)

    items: Mapped[list["MemoryArchiveRestoreItemModel"]] = relationship(
        "MemoryArchiveRestoreItemModel",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class MemoryArchiveRestoreItemModel(Base):
    """记忆归档恢复条目账本。"""

    __tablename__ = "memory_archive_restore_items"
    __table_args__ = (
        Index("ix_memory_archive_restore_items_batch_section", "batch_id", "section"),
        Index("ix_memory_archive_restore_items_batch_status", "batch_id", "status"),
        Index("ix_memory_archive_restore_items_target", "item_kind", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("memory_archive_restore_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    item_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    rollback_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rollback_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)

    batch: Mapped["MemoryArchiveRestoreBatchModel"] = relationship(
        "MemoryArchiveRestoreBatchModel",
        back_populates="items",
    )
