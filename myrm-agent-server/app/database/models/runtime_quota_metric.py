"""Runtime quota and browser compute telemetry models.

[INPUT]
- models.base::Base (POS: ORM base model)

[OUTPUT]
- SearchQuotaRecord: Free search provider monthly quota tracking and self-healing anchor model
- BrowserRuntimeRecord: Browser automation runtime duration and network bandwidth ledger model

[POS]
Database models for observability roadmap: tracks free-tier search provider limits and browser compute cost.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SearchQuotaRecord(Base):
    """Monthly search provider quota ledger with self-healing 429 recalibration."""

    __tablename__ = "search_quota_records"
    __table_args__ = (
        Index("ix_search_quota_provider_month", "provider", "year_month", unique=True),
        Index("ix_search_quota_year_month", "year_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    is_depleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_depleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BrowserRuntimeRecord(Base):
    """Session-level and monthly browser automation compute and network transfer ledger."""

    __tablename__ = "browser_runtime_records"
    __table_args__ = (
        Index("ix_browser_runtime_year_month", "year_month"),
        Index("ix_browser_runtime_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active_compute_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bytes_transferred: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
