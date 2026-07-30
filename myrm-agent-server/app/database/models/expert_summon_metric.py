"""
[INPUT] models.base::Base (POS: ORM base model)
[OUTPUT] ExpertSummonMetricEvent: expert summon funnel observability event model
[POS] Stores template summon funnel events for conversion and ROI measurement.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExpertSummonMetricEvent(Base):
    """Expert template summon funnel event."""

    __tablename__ = "expert_summon_metric_events"
    __table_args__ = (
        Index("ix_expert_summon_metrics_created_at", "created_at"),
        Index("ix_expert_summon_metrics_event_type_created_at", "event_type", "created_at"),
        Index("ix_expert_summon_metrics_surface_created_at", "surface", "created_at"),
        Index("ix_expert_summon_metrics_context_created_at", "context_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    surface: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    context_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    trigger: Mapped[str | None] = mapped_column(String(32), nullable=True)
    template_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    from_search: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    used_use_case: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    query_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
