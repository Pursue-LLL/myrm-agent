"""ORM model for outbound lifecycle webhooks.

[POS] Stores user-configured outbound webhook endpoints for agent lifecycle events.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LifecycleWebhookModel(Base):
    """Lifecycle outbound webhook target configuration."""

    __tablename__ = "lifecycle_webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events_json: Mapped[list[str]] = mapped_column("events", JSON, default=list)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
