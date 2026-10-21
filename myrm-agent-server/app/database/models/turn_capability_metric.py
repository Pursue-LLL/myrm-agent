"""
[INPUT] models.base::Base (POS: ORM base model)
[OUTPUT] TurnCapabilityMetricEvent: per-turn capability observability event model
[POS] Stores one-turn Skill/MCP override events for usage and ROI measurement.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TurnCapabilityMetricEvent(Base):
    """One-turn capability override observability event."""

    __tablename__ = "turn_capability_metric_events"
    __table_args__ = (
        Index("ix_turn_capability_metrics_created_at", "created_at"),
        Index("ix_turn_capability_metrics_event_type_created_at", "event_type", "created_at"),
        Index("ix_turn_capability_metrics_context_created_at", "context_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    context_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    selected_skill_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_mcp_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_skill_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_mcp_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
