"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] CalendarEventModel: 日历事件模型
[POS] 日历事件域模型。管理用户日历事件的创建、查询、更新和删除。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CalendarEventModel(Base):
    """Calendar event for user productivity and agent scheduling."""

    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Recurrence rule (RFC 5545 RRULE string, e.g. "FREQ=WEEKLY;BYDAY=MO,WE,FR")
    rrule: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Color for frontend display (hex string, e.g. "#4F46E5")
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    # e.g. "manual", "agent", "import"
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Reminder (minutes before event)
    reminder_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="confirmed", nullable=False)
    # "confirmed", "tentative", "cancelled"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
