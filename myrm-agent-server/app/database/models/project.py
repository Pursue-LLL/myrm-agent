"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] Project: 会话项目/文件夹分组
[POS] 项目域模型。管理用户创建的项目，用于组织会话。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Project(Base):
    """项目表 — 用于对会话进行主题分组"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#7cb9ff")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
