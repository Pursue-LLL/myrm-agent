"""ORM model for A2A (Agent-to-Agent) trusted peers.

[POS] Stores user-configured remote A2A peer registries and their credentials.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class A2APeerModel(Base):
    """A2A trusted remote peer configuration model."""

    __tablename__ = "a2a_peers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(String(32), default="bearer", nullable=False)
    encrypted_auth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_probe_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cached_card_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

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
