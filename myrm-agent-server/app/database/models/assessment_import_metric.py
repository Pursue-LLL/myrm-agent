"""
[INPUT] models.base::Base (POS: ORM base model)
[OUTPUT] AssessmentImportMetricEvent: assessment import funnel observability event model
[POS] Stores milestone import funnel events for conversion and failure diagnostics.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AssessmentImportMetricEvent(Base):
    """Assessment import funnel observability event."""

    __tablename__ = "assessment_import_metric_events"
    __table_args__ = (
        Index("ix_assessment_import_metrics_created_at", "created_at"),
        Index("ix_assessment_import_metrics_event_type_created_at", "event_type", "created_at"),
        Index("ix_assessment_import_metrics_surface_created_at", "surface", "created_at"),
        Index("ix_assessment_import_metrics_trigger_created_at", "trigger", "created_at"),
        Index("ix_assessment_import_metrics_context_created_at", "context_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    surface: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    context_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
