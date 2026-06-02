"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[INPUT] models.agent::Agent (POS: Agent 配置域模型)
[OUTPUT] AgentProfileHistory: Agent 配置版本审计记录
[POS] 乐观锁 version 递增时的审计轨迹 + 聊天 Prompt 编辑器只读版本列表（/user-agents/{id}/history）。
      持久 rollback SSOT 为 AgentProfileSnapshot，非本表。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .agent import Agent


class AgentProfileHistory(Base):
    """Agent 配置版本审计（乐观锁 + Prompt 浏览，非 rollback SSOT）"""

    __tablename__ = "agent_profile_history"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Snapshot fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality_style: Mapped[str] = mapped_column(String(32), nullable=False)

    snapshot_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship("Agent")
