"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] ChannelMessageModel: 多渠道入站明细持久化模型
[POS] 渠道数据平面（Channel Data Plane）DWD 明细实体。记录所有通过渠道接收的合规消息，支持凭据脱敏、触发状态标记与长期知识提炼筛选。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChannelMessageModel(Base):
    """Channel Data Plane DWD message ledger.

    Persists all inbound channel messages after security redaction, decouples
    real-time execution triggers from offline background context retention.
    """

    __tablename__ = "channel_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_trigger: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_self: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)
    is_group: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    learning_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_channel_messages_chat_created", "channel", "chat_id", "created_at"),
        Index("ix_channel_messages_learning_created", "learning_eligible", "created_at"),
    )
