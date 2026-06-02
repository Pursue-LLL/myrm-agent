"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] UserConfig: 用户配置模型
[OUTPUT] ConfigAuditLog: 配置审计日志模型
[POS] 用户配置域模型。存储用户键值对配置和历史变更审计日志，支持版本号和加密。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ConfigAuditLog(Base):
    """配置审计日志表 (Configuration Time-Machine)
    
    记录每次配置变更的历史，支持回滚。
    """
    __tablename__ = "config_audit_logs"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserConfig(Base):
    """用户配置表

    每个 (user_id, config_key) 唯一。版本号格式: 时间戳_计数器 (如 1706000000000_0)。
    """

    __tablename__ = "user_configs"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    config_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    last_device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("config_key", name="uq_config_key"),)
