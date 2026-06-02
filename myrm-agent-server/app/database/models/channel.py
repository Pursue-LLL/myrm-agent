"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] ChannelPairingModel: 频道身份映射
[POS] 频道域模型。映射外部频道身份到系统用户账户。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChannelPairingModel(Base):
    """Maps external channel identities to system user accounts."""

    __tablename__ = "channel_pairings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("channel", "sender_id", name="uq_channel_sender"),)
