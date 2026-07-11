"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] WebPushSubscription: Web Push VAPID 订阅
[POS] Web Push 域模型。存储浏览器 Push 订阅信息，供离线通知推送使用。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WebPushSubscription(Base):
    """Web Push 订阅表

    每行对应一个浏览器的 PushSubscription 对象。
    endpoint_hash 使用 SHA-256 前 32 字符作为主键，确保唯一且可快速查找。
    """

    __tablename__ = "web_push_subscriptions"

    endpoint_hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
