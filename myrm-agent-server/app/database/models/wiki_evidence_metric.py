"""
[INPUT] models.base::Base (POS: ORM base model)
[OUTPUT] WikiEvidenceMetricEvent: wiki evidence observability event model
[POS] Stores evidence-surface/open/close/query/outcome events for ROI measurement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WikiEvidenceMetricEvent(Base):
    """Evidence interaction event for wiki verification analytics."""

    __tablename__ = "wiki_evidence_metric_events"
    __table_args__ = (
        Index("ix_wiki_evidence_metrics_created_at", "created_at"),
        Index("ix_wiki_evidence_metrics_event_type_created_at", "event_type", "created_at"),
        Index("ix_wiki_evidence_metrics_context_created_at", "context_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    surface: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    context_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_evidence: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
