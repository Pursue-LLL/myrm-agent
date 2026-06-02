"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] MessageFilterConfig, MessageFilterRule, MessageFilterAudit, MessageFilterConfigHistory
[POS] 消息过滤域模型。管理消息过滤器配置、规则、审计日志和配置变更历史。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MessageFilterConfig(Base):
    """消息过滤器配置表"""

    __tablename__ = "message_filter_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pii_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="redact")
    whitelist_api_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    audit_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MessageFilterRule(Base):
    """消息过滤规则表"""

    __tablename__ = "message_filter_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MessageFilterAudit(Base):
    """消息过滤审计日志表"""

    __tablename__ = "message_filter_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filter_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MessageFilterConfigHistory(Base):
    """消息过滤器配置历史表"""

    __tablename__ = "message_filter_config_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
