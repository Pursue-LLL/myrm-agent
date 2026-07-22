"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] UserToolAllowlist, RiskRule, RiskHit, SecurityProfile, SkillPermissionGrant, SkillPermissionUsageLog
[POS] 安全域模型。管理工具白名单(HITL)、风控规则/命中记录和 Skill 权限授予/使用日志。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserToolAllowlist(Base):
    """工具白名单表（HITL 审批系统）

    四种粒度：权限级别、工具级别、精确匹配、命令模式匹配。
    使用空字符串代替 NULL 确保 UNIQUE 约束生效。
    """

    __tablename__ = "user_tool_allowlist"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    permission: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    tool_args_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    command_pattern: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "permission",
            "tool_name",
            "tool_args_hash",
            "command_pattern",
            name="uq_user_allowlist_final",
        ),
    )


class RiskRule(Base):
    """风控规则表

    内置规则 (is_builtin=True) 只能启用/禁用，不能删除。
    """

    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="custom", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RiskHit(Base):
    """风控命中记录表"""

    __tablename__ = "risk_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    match_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SkillPermissionGrant(Base):
    """Skill 权限授予记录表"""

    __tablename__ = "skill_permission_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(50), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("skill_id", "permission", name="uq_user_skill_permission"),)


class SkillPermissionUsageLog(Base):
    """Skill 权限使用日志表"""

    __tablename__ = "skill_permission_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(500), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    deny_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SecurityProfile(Base):
    """安全配置 Profile 表

    存储命名的安全配置方案，用户可在不同场景间快速切换。
    内置 Profile (is_builtin=True) 不可删除，仅可复制和修改副本。

    profile_key 格式: "readonly" | "workspace" | "full_access" | 用户自定义名称
    config_json 结构: SecurityConfig 序列化后的 JSON dict
    """

    __tablename__ = "security_profiles"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
