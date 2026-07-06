"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[INPUT] app.ai_agents.personality_templates::DEFAULT_PERSONALITY_STYLE (POS: Agent 人格风格模板)
[OUTPUT] Agent: Agent 配置, AgentSecret: Agent 加密密钥
[POS] Agent 配置域模型。管理 Agent 基本信息、模型配置、技能绑定和加密密钥。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE

from .base import Base


class Agent(Base):
    """Agent 配置表 (Database Profile Backend)"""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    home_directory: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(20), default="individual", nullable=False)

    model_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model_selection: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    skill_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mounted_skill_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    skill_configs: Mapped[dict[str, dict] | None] = mapped_column(JSON, nullable=True)
    mcp_servers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mcp_tool_selections: Mapped[dict[str, list[str]] | None] = mapped_column(JSON, nullable=True)
    subagent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    enabled_builtin_tools: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    browser_engine: Mapped[str | None] = mapped_column(String(50), nullable=True)  # deprecated: unread legacy column
    browser_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dialog_policy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_recording: Mapped[str | None] = mapped_column(String(20), nullable=True)
    auto_restore_domains: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    security_overrides: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    prompt_mode: Mapped[str] = mapped_column(String(20), default="full", nullable=False)
    personality_style: Mapped[str] = mapped_column(String(32), default=DEFAULT_PERSONALITY_STYLE, nullable=False)
    suggestion_prompts: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    memory_decay_profile: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    max_iterations: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    workspace_policy: Mapped[str] = mapped_column(String(50), default="INHERIT_REQUESTER", nullable=False)
    memory_policy: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    engine_params: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    command_bindings: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    openapi_services: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    session_policy: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    notify_targets: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    tool_gateway_config: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    cron_post_run_verify: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_built_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    secrets: Mapped[list["AgentSecret"]] = relationship("AgentSecret", back_populates="agent", cascade="all, delete-orphan")


class AgentSecret(Base):
    """Agent 密钥表 (AES-256-GCM 加密存储)"""

    __tablename__ = "agent_secrets"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    secret_key: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent: Mapped["Agent"] = relationship("Agent", back_populates="secrets")

    __table_args__ = (UniqueConstraint("agent_id", "secret_key", name="uq_agent_secret_key"),)


class AgentProfileSnapshot(Base):
    """Agent Profile 历史快照表 (用于防砖和回滚)"""

    __tablename__ = "agent_profile_snapshots"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    snapshot_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
