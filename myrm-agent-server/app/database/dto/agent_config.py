"""[INPUT]
- pydantic BaseModel / Field / model_validator (POS: 模型基类)
- .literals (POS: 存储值词表)

[OUTPUT]
- ModelSelection, AgentMemoryPolicyConfig, AgentSessionPolicyConfig, SkillConfig,
  CommandBindingConfig, ToolGatewayConfigDTO

[POS]
Data transfer objects: nested agent config models shared by agent request shapes.
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.toolkits.memory.config import MemoryScopeLevel, MemoryWritePolicy
from pydantic import BaseModel, Field, model_validator

from .literals import (
    SessionResetModeLiteral,
)


class ModelSelection(BaseModel):
    """模型选择引用"""

    providerId: str = Field(..., description="提供商 ID")
    model: str = Field(..., description="模型名称")
    fallbackProviderId: str | None = Field(default=None, description="备选提供商 ID")
    fallbackModel: str | None = Field(default=None, description="备选模型名称")
    safetyFallbackProviderId: str | None = Field(default=None, description="安全备选提供商 ID")
    safetyFallbackModel: str | None = Field(default=None, description="安全备选模型名称")
    modelKwargs: dict[str, object] | None = Field(default=None, description="模型调用参数 (temperature, top_p, max_tokens 等)")
    routingEnabled: bool | None = Field(default=None, description="Per-agent Smart Routing 开关")
    lightProviderId: str | None = Field(default=None, description="Per-agent 轻量路由提供商 ID")
    lightModel: str | None = Field(default=None, description="Per-agent 轻量路由模型")
    reasoningProviderId: str | None = Field(default=None, description="Per-agent 推理路由提供商 ID")
    reasoningModel: str | None = Field(default=None, description="Per-agent 推理路由模型")


class AgentMemoryPolicyConfig(BaseModel):
    """Agent 记忆读写边界策略。"""

    agent_id: str | None = Field(default=None, description="Override agent scope identifier")
    channel_id: str | None = Field(default=None, description="Override channel scope identifier")
    conversation_id: str | None = Field(default=None, description="Override conversation scope identifier")
    task_id: str | None = Field(default=None, description="Override task scope identifier")
    read_scopes: list[MemoryScopeLevel] | None = Field(default=None, description="Visible memory scope levels for recall")
    write_policy: MemoryWritePolicy = Field(
        default=MemoryWritePolicy.INHERIT,
        description="Target scope for new private memories",
    )
    allow_l3_extraction: bool = Field(
        default=True,
        description="Whether background L3 LLM memory extraction is allowed",
    )
    auto_cleanup: bool = Field(
        default=False,
        description="Whether ephemeral session/task state is cleaned up upon task end",
    )


class AgentSessionPolicyConfig(BaseModel):
    """Per-agent IM session reset policy override.

    When set on an agent, overrides the user's global sessionPolicy
    from personalSettings for that specific agent.
    """

    mode: SessionResetModeLiteral = Field(default="daily", description="Session segmentation strategy: persistent | daily | idle")
    daily_reset_hour: int = Field(default=4, description="UTC hour for daily reset (0-23)", ge=0, le=23)
    idle_minutes: int = Field(default=120, description="Idle threshold in minutes for idle mode", ge=1, le=10080)


class SkillConfig(BaseModel):
    """Skill configuration for a specific agent"""

    is_core: bool = Field(default=False, description="Whether this skill is a core skill (always injected)")
    instance_name: str | None = Field(
        default=None,
        description=(
            "Bound SkillInstance name for this agent (multi-instance skills). "
            "When unset, singleton or 'default' instance is auto-selected."
        ),
        max_length=64,
    )


class CommandBindingConfig(BaseModel):
    """Slash command binding to one or more Skills for IM channels."""

    command_name: str = Field(
        ...,
        description="Command name without slash (e.g. 'daily-report')",
        max_length=50,
    )
    skill_ids: list[str] = Field(default_factory=list, description="Target Skill IDs (single or bundle)")
    description: str = Field(default="", description="User-facing description shown in /help")
    aliases: list[str] = Field(default_factory=list, description="Alternative command names")
    instruction: str = Field(default="", description="Ephemeral guidance for bundle execution")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_skill_id(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible: convert legacy ``skill_id`` to ``skill_ids``."""
        if not isinstance(data, dict):
            return data
        if "skill_id" in data and "skill_ids" not in data:
            sid = data.pop("skill_id")
            data["skill_ids"] = [sid] if sid else []
        return data


class ToolGatewayConfigDTO(BaseModel):
    """Tool Gateway configuration DTO."""

    use_gateway: bool = Field(default=False, description="Whether to use the Unified Tool Gateway")
    gateway_url: str | None = Field(default=None, description="Base URL of the Unified Tool Gateway")
    auth_token: str | None = Field(default=None, description="Authentication token for the gateway")
