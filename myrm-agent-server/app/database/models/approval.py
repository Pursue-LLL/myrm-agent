"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] ApprovalRecord
[POS] 统一审批记录模型。存储所有被拦截的执行节点（如高危Shell、敏感记忆、技能草稿）的挂起状态，替代散落的 Draft。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApprovalRecord(Base):
    """统一审批记录表"""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # 对于 LangGraph 中断，记录 thread_id 才能唤醒
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    action_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # e.g. skill_patch, memory_mutation, shell_command
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)

    # 存储 ApprovalContract 的 payload
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, APPROVED, REJECTED
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
