"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] SystemNotification: 系统通知
[POS] 通知域模型。存储系统级异步通知，供前端通知中心展示。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemNotification(Base):
    """系统通知表

    用于异步长耗时任务失败、系统维护等通知。
    """

    __tablename__ = "system_notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
