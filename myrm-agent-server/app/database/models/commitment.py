"""
[INPUT] models.base::Base (POS: ORM model base class)
[OUTPUT] CommitmentModel: Implicit commitment/follow-up tracking
[POS] ORM model for commitment records extracted from conversations.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CommitmentModel(Base):
    """Implicit commitment record extracted from conversation."""

    __tablename__ = "commitments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), default="web", nullable=False)

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    due_earliest_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    due_latest_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    due_timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)

    source_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
