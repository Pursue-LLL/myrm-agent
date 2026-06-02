"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] AgentTurn: Agent 执行轮次, AgentEvent: Agent 执行事件
[POS] Agent 事件域模型。记录 Agent 执行过程的轮次和细粒度事件，用于 UI 展示和审计。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .chat import Chat


class AgentTurn(Base):
    """Agent 执行轮次表

    每次用户输入到 Agent 完成响应为一个 Turn。
    层级结构：Chat (session) → Turn → Event
    """

    __tablename__ = "agent_turns"
    __table_args__ = (Index("ix_agent_turns_chat_id_created_at", "chat_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)

    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    spawn_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spawned_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    chat: Mapped["Chat"] = relationship("Chat", lazy="selectin")

    events: Mapped[list["AgentEvent"]] = relationship(
        "AgentEvent", back_populates="turn", cascade="all, delete-orphan", lazy="selectin"
    )


class AgentEvent(Base):
    """Agent 执行事件表

    事件类型: tool_call_start/end, command_start/output/end,
    file_diff, artifact_created, permission_request/response,
    thinking, assistant_message, error
    """

    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    turn: Mapped["AgentTurn"] = relationship("AgentTurn", back_populates="events")
