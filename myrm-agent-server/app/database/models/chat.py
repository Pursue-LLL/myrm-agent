"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] Chat: 聊天会话, Message: 消息, ConversationFork: 对话分支
[POS] 会话与消息域模型。管理聊天会话、消息记录和对话分支。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Chat(Base):
    """聊天会话表"""

    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_mode: Mapped[str] = mapped_column(String(50), default="fast", nullable=False)

    source: Mapped[str] = mapped_column(String(50), default="web", nullable=False, index=True)
    channel_session_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    compacted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    compacted_before_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compacted_tokens_saved: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session_notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Store JIT ephemeral subagents for session resume and crash recovery
    ephemeral_subagents: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Persisted loaded skill names for session skill contract (survives compaction / history trim)
    session_loaded_skill_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Per-chat working directory: agent CWD and sandbox boundary
    workspace_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Original repo root when sandbox (git worktree) is active
    sandbox_base_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Project grouping: organize chats into user-defined projects
    project_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Pinned thread support: user can pin up to 9 chats for quick access
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pin_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Incognito mode: hide from sidebar, do not persist to memory
    is_incognito: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    # Usage Analytics Summary (Updated by Server on session end/sync)
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Share: NULL = not revoked (share link active if token valid), non-NULL = revoked at
    share_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft-delete: NULL = active, non-NULL = trashed at this timestamp
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("channel_session_key", name="uq_chat_channel_session"),)


class Message(Base):
    """消息表"""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id_created_at", "chat_id", "created_at"),
        Index("ix_messages_sent_at", "sent_at"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=False)
    sent_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    sibling_group_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")


class ConversationFork(Base):
    """对话分支表

    Direct Copy (非COW): O(1)查询性能，牺牲少量存储。
    child_chat_id 为主键：每个子会话唯一对应一个父会话。
    """

    __tablename__ = "conversation_forks"

    child_chat_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parent_chat_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fork_checkpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fork_message_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfflineDurableTask(Base):
    """持久化离线任务表

    记录因客户端断线而转入后台托管的长耗时任务（如 deep_research）。
    在 Server 意外重启时，通过扫描此表恢复任务执行。
    """

    __tablename__ = "offline_durable_tasks"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    action_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    serialized_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
