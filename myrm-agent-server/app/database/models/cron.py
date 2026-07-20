"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] CronJobModel: 定时任务(含 triggers JSON), CronRunModel: 任务执行记录(含 trigger_source), MonitorStateModel: 增量监控状态
[POS] 定时任务域模型。管理 Cron 任务定义、执行记录和增量监控状态。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CronJobModel(Base):
    """Scheduled cron job."""

    __tablename__ = "cron_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)

    schedule: Mapped[dict] = mapped_column(JSON, nullable=False)

    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_condition_script: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_delivery: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    required_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tools_allowed: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_roots: Mapped[list | None] = mapped_column(JSON, nullable=True)

    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    retry_backoff_ms: Mapped[int] = mapped_column(Integer, default=30000, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    misfire_grace_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_fires: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fire_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    session_target: Mapped[str] = mapped_column(String(20), default="isolated", nullable=False)
    delete_after_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    run_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    deduplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skip_if_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    context_from: Mapped[list | None] = mapped_column(JSON, nullable=True)

    failure_alert: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    monitor_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    triggers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pre_condition_script: Mapped[str | None] = mapped_column(Text, nullable=True)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    runs: Mapped[list["CronRunModel"]] = relationship("CronRunModel", back_populates="job", cascade="all, delete-orphan")


class CronRunModel(Base):
    """Single execution record for a cron job."""

    __tablename__ = "cron_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("cron_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    integrity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["CronJobModel"] = relationship("CronJobModel", back_populates="runs")


class MonitorStateModel(Base):
    """Incremental monitor state for cron jobs."""

    __tablename__ = "monitor_states"

    job_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("cron_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    monitor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    ttl_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reset_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
