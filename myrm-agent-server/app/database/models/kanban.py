"""
[INPUT] models.base::Base (POS: ORM model base class)
[OUTPUT] KanbanBoardModel: Kanban board, KanbanTaskModel: Kanban task,
        KanbanTaskRunModel: Execution run, KanbanTaskEventModel: Lifecycle event,
        KanbanTaskEdgeModel: Task dependency edge
[POS] Kanban domain ORM models. Manages boards, tasks, runs, events,
and dependency edges for persistent multi-task scheduling.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class KanbanBoardModel(Base):
    """Kanban board — top-level grouping entity."""

    __tablename__ = "kanban_boards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    max_concurrent_tasks: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )
    heartbeat_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    zombie_timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=120, nullable=False
    )
    max_retries_per_task: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )
    auto_block_after_consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    specify_max_tokens: Mapped[int] = mapped_column(
        Integer, default=6000, nullable=False, server_default="6000",
    )
    auto_specify_on_create: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0",
    )
    default_workdir: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tasks: Mapped[list["KanbanTaskModel"]] = relationship(
        "KanbanTaskModel", back_populates="board", cascade="all, delete-orphan"
    )


class KanbanTaskModel(Base):
    """Kanban task — unit of work on a board."""

    __tablename__ = "kanban_tasks"
    __table_args__ = (
        Index("ix_kanban_tasks_board_status", "board_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("kanban_boards.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="backlog", nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="normal", nullable=False,
    )

    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    goal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("kanban_tasks.id", ondelete="SET NULL"), nullable=True
    )

    workspace_path: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None,
    )
    branch: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None,
    )

    max_runtime_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    block_cycle_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0",
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    progress_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scheduled_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    extra_skill_ids_json: Mapped[list | None] = mapped_column(
        "extra_skill_ids", JSON, nullable=True, default=None,
    )
    attachment_ids_json: Mapped[list | None] = mapped_column(
        "attachment_ids", JSON, nullable=True, default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    board: Mapped["KanbanBoardModel"] = relationship(
        "KanbanBoardModel", back_populates="tasks"
    )
    parent: Mapped["KanbanTaskModel | None"] = relationship(
        "KanbanTaskModel",
        back_populates="children",
        remote_side="KanbanTaskModel.id",
        foreign_keys="KanbanTaskModel.parent_task_id",
    )
    children: Mapped[list["KanbanTaskModel"]] = relationship(
        "KanbanTaskModel",
        back_populates="parent",
        foreign_keys="KanbanTaskModel.parent_task_id",
    )
    runs: Mapped[list["KanbanTaskRunModel"]] = relationship(
        "KanbanTaskRunModel", back_populates="task", cascade="all, delete-orphan"
    )
    events: Mapped[list["KanbanTaskEventModel"]] = relationship(
        "KanbanTaskEventModel", back_populates="task", cascade="all, delete-orphan"
    )


class KanbanTaskRunModel(Base):
    """Execution run — independent record per attempt."""

    __tablename__ = "kanban_task_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    task: Mapped["KanbanTaskModel"] = relationship(
        "KanbanTaskModel", back_populates="runs"
    )


class KanbanTaskEventModel(Base):
    """Lifecycle event — persistent audit trail."""

    __tablename__ = "kanban_task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column("payload", JSON, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["KanbanTaskModel"] = relationship(
        "KanbanTaskModel", back_populates="events"
    )


class KanbanTaskEdgeModel(Base):
    """Task dependency edge — parent→child DAG constraint."""

    __tablename__ = "kanban_task_edges"
    __table_args__ = (
        UniqueConstraint("parent_task_id", "child_task_id", name="uq_kanban_edge"),
        Index("ix_kanban_edges_child", "child_task_id"),
        Index("ix_kanban_edges_parent", "parent_task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_task_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_task_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("kanban_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
