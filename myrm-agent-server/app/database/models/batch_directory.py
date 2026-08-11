"""
[INPUT] models.base::Base (POS: ORM model base class)
[OUTPUT] BatchDirectoryProjectModel: Batch directory parallel prompt project
[POS] BatchDirectory domain ORM model. Persists batch-level metadata for
"same prompt × N directories" parallel runs; per-directory tasks live in
kanban_tasks and are linked via metadata `batch_project_id`.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BatchDirectoryProjectModel(Base):
    """Batch directory parallel prompt project — lightweight orchestration record.

    Executes the *same* prompt across *multiple* directories in parallel.
    Execution is fully delegated to the Kanban dispatcher/runner: each target
    directory becomes one Kanban task (``workspace_path`` set, metadata tagged
    with ``batch_project_id``). This table only stores batch-level metadata and
    running aggregates so the board remains the single source of task truth.
    """

    __tablename__ = "batch_directory_projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    board_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("kanban_boards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )
    concurrency: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_runtime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_approval: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="0",
    )
    notify_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="1",
    )

    directories_json: Mapped[list | None] = mapped_column("directories", JSON, nullable=True)
    artifact_patterns_json: Mapped[list | None] = mapped_column(
        "artifact_patterns",
        JSON,
        nullable=True,
    )

    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
