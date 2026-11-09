"""[INPUT]
- .agent_config (POS: nested agent config models)
- .literals (POS: stored value vocabularies)

[OUTPUT]
- AgentBase, AgentCreate, AgentUpdate, AgentResponse, AgentProfileSnapshotItem, AgentListItem

[POS]
Data transfer objects: agent request/response shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent.builtin_specs.builtin_tool_validation import OptionalBuiltinTools

from .agent_config import (
    AgentMemoryPolicyConfig,
    AgentSessionPolicyConfig,
    CommandBindingConfig,
    ModelSelection,
    SkillConfig,
    ToolGatewayConfigDTO,
)
from .literals import (
    AgentTypeLiteral,
    MemoryDecayProfileLiteral,
    MemoryExtractionPresetLiteral,
    PromptModeLiteral,
    SecurityPresetLiteral,
    WorkspacePolicyLiteral,
)


class AgentBase(BaseModel):
    """智能体基础模型"""

    name: str = Field(..., description="智能体名称", max_length=255)
    description: str | None = Field(default=None, description="智能体描述")
    avatar_url: str | None = Field(default=None, description="智能体头像/图标 URL", max_length=500)
    home_directory: str | None = Field(default=None, description="Agent Home 目录路径", max_length=500)
    is_built_in: bool = Field(default=False, description="是否为内置 Agent")
    system_prompt: str | None = Field(default=None, description="系统指令/用户自定义提示词")
    mcp_ids: list[str] = Field(default=[], description="关联的 MCP 配置 ID 列表")
    mcp_tool_selections: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Per-MCP-server tool whitelist: {server_name: [tool_name...]}. "
            "A server absent here = all its tools enabled. Empty list = handled by frontend "
            "(0 tools deselects the server). Drives MCPConfig.tool_include at agent build time."
        ),
    )
    skill_ids: list[str] = Field(default=[], description="关联的技能 ID 列表")
    mounted_skill_ids: list[str] = Field(default=[], description="挂载的其他 Agent 专属技能 ID 列表")
    skill_configs: dict[str, SkillConfig] | None = Field(default=None, description="技能的个性化配置 (如 is_core)")
    enabled_builtin_tools: OptionalBuiltinTools = Field(default=None, description="启用的内置工具 ID 列表")
    browser_source: str | None = Field(
        default=None,
        description="浏览器获取方式: 'launch'(新建)、'connect'(CDP)、'extension'(扩展桥接)、'auto'(自动)、'remote'(远程)。为空则使用系统默认。",
    )
    dialog_policy: str | None = Field(
        default=None,
        description="弹窗处理策略: 'smart'(智能)、'auto_accept'(自动确认)、'auto_dismiss'(自动取消)、'wait_for_agent'(等待Agent处理)。为空则使用默认smart。",
    )
    session_recording: str | None = Field(
        default=None,
        description="浏览器会话录制模式: 'off'(关闭)、'on_failure'(仅失败时保留)、'always'(始终保留)。为空则使用默认off。",
    )
    model_selection: ModelSelection | None = Field(default=None, description="绑定的模型选择")
    security_overrides: dict[str, object] | None = Field(default=None, description="Per-agent security policy overrides")
    default_security_preset: SecurityPresetLiteral | None = Field(
        default=None,
        description=(
            "Per-agent default chat security preset (hitl/accept_edits/explore). "
            "New sessions bound to this agent start with this preset; the user can "
            "still override it per-session."
        ),
    )
    required_capabilities: list[str] = Field(
        default=[],
        description="该 Agent 运行所需的渠道能力列表（如 media, voice_message）",
    )
    memory_decay_profile: MemoryDecayProfileLiteral = Field(default="normal", description="Memory forgetting decay speed")
    memory_extraction_preset: MemoryExtractionPresetLiteral = Field(
        default="auto", description="Domain extraction preset for memory precision"
    )
    agent_type: AgentTypeLiteral = Field(default="individual", description="Agent type: individual or team (leader)")
    allow_discovery: bool = Field(default=True, description="是否允许被主Agent通过动态名册发现并委派")
    subagent_ids: list[str] = Field(default=[], description="可委托的子智能体 ID 列表")
    max_iterations: int | None = Field(default=None, description="最大迭代次数（None=使用系统默认值）", ge=5, le=500)
    workspace_policy: WorkspacePolicyLiteral = Field(
        default="INHERIT_REQUESTER",
        description="Workspace policy when this agent is used as a delegated subagent",
    )
    memory_policy: AgentMemoryPolicyConfig | None = Field(default=None, description="Agent memory policy")
    session_policy: AgentSessionPolicyConfig | None = Field(
        default=None,
        description="Per-agent IM session reset policy override (overrides global personalSettings.sessionPolicy)",
    )
    engine_params: dict[str, Any] | None = Field(
        default=None,
        description="Advanced engine parameters (e.g. max_tool_calls, max_replan_attempts)",
    )
    auto_restore_domains: list[str] = Field(
        default_factory=list,
        description="Hostnames for which the browser toolkit auto-restores persisted login state",
    )
    suggestion_prompts: list[str] | None = Field(
        default=None,
        description="Custom starter prompts displayed when this agent is active in an empty chat",
    )
    # Pareto preset specific attributes
    is_pareto_preset: bool = Field(default=False, description="是否为帕累托成本/效果前沿预设")
    cost_reduction_ratio: float | None = Field(default=None, description="相较全量顶级闭源模型的估算降本比例 (e.g. 0.70)")
    openapi_services: list[dict[str, object]] = Field(
        default_factory=list,
        description="OpenAPI service configurations for zero-code REST API tool integration",
    )
    command_bindings: list[CommandBindingConfig] | None = Field(
        default=None,
        description="Slash command bindings to Skills for IM channels (e.g. /daily-report -> skill_id)",
    )
    notify_targets: list[dict[str, str]] | None = Field(
        default=None,
        description="Notification targets for channel_notify_tool [{channel, recipient_id, label?}]",
    )
    tool_gateway_config: ToolGatewayConfigDTO | None = Field(
        default=None,
        description="Tool Gateway configuration for third-party tools",
    )
    cron_post_run_verify: bool = Field(
        default=False,
        description="Run adversarial delivery verification after unattended cron agent runs (verifier-only, no worker retry)",
    )
    busy_input_mode: Literal["redirect", "steer", "queue"] | None = Field(
        default=None,
        description="What to do with a new user message while the agent is busy: redirect/steer/queue",
    )
    trusted_desktop_apps: list[dict[str, str]] = Field(
        default_factory=list, description="无人值守运行预信任的桌面应用 [{name, app_id?}]"
    )
    responsibility_scope: str | None = Field(
        default=None,
        description="责任单元职责定义：该 Agent 长期负责什么（治理展示用，不进入系统提示词）",
        max_length=2000,
    )
    owner_label: str | None = Field(
        default=None,
        description="责任单元负责人标注（单机默认本人免填；云托管/分享时必填）",
        max_length=100,
    )
    acceptance_criteria: list[str] | None = Field(
        default=None,
        description="责任单元交付验收条目（结构化可勾选，非自由文本）",
        max_length=20,
    )


class AgentCreate(AgentBase):
    """创建智能体请求模型"""

    pass


class AgentUpdate(BaseModel):
    """更新智能体请求模型"""

    name: str | None = Field(default=None, description="智能体名称", max_length=255)
    description: str | None = Field(default=None, description="智能体描述")
    avatar_url: str | None = Field(default=None, description="智能体头像/图标 URL", max_length=500)
    home_directory: str | None = Field(default=None, description="Agent Home 目录路径", max_length=500)
    is_built_in: bool | None = Field(default=None, description="是否为内置 Agent")
    system_prompt: str | None = Field(default=None, description="系统指令/用户自定义提示词")
    mcp_ids: list[str] | None = Field(default=None, description="关联的 MCP 配置 ID 列表")
    mcp_tool_selections: dict[str, list[str]] | None = Field(
        default=None,
        description="Per-MCP-server tool whitelist: {server_name: [tool_name...]}. None = leave unchanged.",
    )
    skill_ids: list[str] | None = Field(default=None, description="关联的技能 ID 列表")
    mounted_skill_ids: list[str] | None = Field(default=None, description="挂载的其他 Agent 专属技能 ID 列表")
    skill_configs: dict[str, SkillConfig] | None = Field(default=None, description="技能的个性化配置 (如 is_core)")
    enabled_builtin_tools: OptionalBuiltinTools = Field(default=None, description="启用的内置工具 ID 列表")
    browser_source: str | None = Field(
        default=None,
        description="浏览器获取方式: 'launch'/'connect'/'extension'/'auto'/'remote'。None=不修改。",
    )
    dialog_policy: str | None = Field(
        default=None,
        description="弹窗处理策略: 'smart'/'auto_accept'/'auto_dismiss'/'wait_for_agent'。None=不修改。",
    )
    session_recording: str | None = Field(
        default=None,
        description="浏览器会话录制模式: 'off'/'on_failure'/'always'。None=不修改。",
    )
    model_selection: ModelSelection | None = Field(default=None, description="绑定的模型选择")
    security_overrides: dict[str, object] | None = Field(default=None, description="Per-agent security policy overrides")
    default_security_preset: SecurityPresetLiteral | None = Field(
        default=None,
        description="Per-agent default chat security preset. None=不修改。",
    )
    required_capabilities: list[str] = Field(
        default=[],
        description="该 Agent 运行所需的渠道能力列表（如 media, voice_message）",
    )
    memory_decay_profile: MemoryDecayProfileLiteral | None = Field(default=None, description="Memory forgetting decay speed")
    memory_extraction_preset: MemoryExtractionPresetLiteral | None = Field(
        default=None, description="Domain extraction preset for memory precision"
    )
    agent_type: AgentTypeLiteral | None = Field(default=None, description="Agent type: individual or team (leader)")
    allow_discovery: bool | None = Field(default=None, description="是否允许被主Agent通过动态名册发现并委派")
    subagent_ids: list[str] | None = Field(default=None, description="可委托的子智能体 ID 列表")
    max_iterations: int | None = Field(
        default=None,
        description=("最大迭代次数（不传/省略=不修改；显式传 null=恢复系统默认）"),
        ge=5,
        le=500,
    )
    workspace_policy: WorkspacePolicyLiteral | None = Field(
        default=None,
        description="Workspace policy when this agent is used as a delegated subagent",
    )
    memory_policy: AgentMemoryPolicyConfig | None = Field(default=None, description="Agent memory policy")
    session_policy: AgentSessionPolicyConfig | None = Field(
        default=None,
        description="Per-agent IM session reset policy override (null = use global policy)",
    )
    engine_params: dict[str, Any] | None = Field(
        default=None,
        description="Advanced engine parameters (e.g. max_tool_calls, max_replan_attempts)",
    )
    auto_restore_domains: list[str] | None = Field(
        default=None,
        description=(
            "Browser hostnames for persisted login auto-restore. "
            "Send null or omit the field to leave the stored value unchanged. "
            "Send an empty list [] to clear all configured hostnames."
        ),
    )
    suggestion_prompts: list[str] | None = Field(
        default=None,
        description="Custom starter prompts displayed when this agent is active in an empty chat",
    )
    is_pareto_preset: bool | None = Field(default=None, description="是否为帕累托成本/效果前沿预设")
    cost_reduction_ratio: float | None = Field(default=None, description="相较全量顶级闭源模型的估算降本比例")
    openapi_services: list[dict[str, object]] | None = Field(
        default=None,
        description="OpenAPI service configurations for zero-code REST API tool integration",
    )
    command_bindings: list[CommandBindingConfig] | None = Field(
        default=None,
        description="Slash command bindings to Skills for IM channels",
    )
    notify_targets: list[dict[str, str]] | None = Field(
        default=None,
        description="Notification targets for channel_notify_tool [{channel, recipient_id, label?}]",
    )
    tool_gateway_config: ToolGatewayConfigDTO | None = Field(
        default=None,
        description="Tool Gateway configuration for third-party tools",
    )
    cron_post_run_verify: bool | None = Field(
        default=None,
        description="Run adversarial delivery verification after unattended cron agent runs",
    )
    busy_input_mode: Literal["redirect", "steer", "queue"] | None = Field(
        default=None,
        description="What to do with a new user message while the agent is busy: redirect/steer/queue. None=不修改。",
    )
    trusted_desktop_apps: list[dict[str, str]] | None = Field(
        default=None, description="无人值守运行预信任的桌面应用 [{name, app_id?}]。None=不修改。"
    )
    responsibility_scope: str | None = Field(
        default=None,
        description="责任单元职责定义。None=不修改；传空字符串=清空。",
        max_length=2000,
    )
    owner_label: str | None = Field(
        default=None,
        description="责任单元负责人标注。None=不修改；传空字符串=清空。",
        max_length=100,
    )
    acceptance_criteria: list[str] | None = Field(
        default=None,
        description="责任单元交付验收条目。None=不修改；传空列表=清空。",
        max_length=20,
    )


class AgentResponse(AgentBase):
    """智能体响应模型"""

    id: str = Field(..., description="智能体 ID")
    user_id: str = Field(..., description="用户 ID")
    snapshot_count: int = Field(default=0, description="可用配置快照数量")
    snapshot_saved: bool | None = Field(
        default=None,
        description="本次更新是否成功写入变更前快照（仅 PUT 响应）",
    )
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class AgentProfileSnapshotItem(BaseModel):
    """Agent 配置快照列表项"""

    id: str = Field(..., description="快照 ID")
    agent_id: str = Field(..., description="智能体 ID")
    reason: str | None = Field(default=None, description="快照原因")
    snapshot_data: dict[str, object] = Field(..., description="快照配置数据")
    created_at: datetime = Field(..., description="创建时间")


class AgentListItem(BaseModel):
    """智能体列表项模型"""

    id: str = Field(..., description="智能体 ID")
    name: str = Field(..., description="智能体名称")
    description: str | None = Field(default=None, description="智能体描述")
    avatar_url: str | None = Field(default=None, description="智能体头像/图标 URL")
    is_built_in: bool = Field(default=False, description="是否为内置 Agent")
    agent_type: AgentTypeLiteral = Field(default="individual", description="Agent type")
    prompt_mode: PromptModeLiteral = Field(
        default="full", description="Prompt mode, set by the system: search for the built-in search agents, otherwise full"
    )
    subagent_ids: list[str] | None = Field(default=None, description="关联子智能体 ID 列表")
    enabled_builtin_tools: list[str] | None = Field(
        default=None,
        description="Enabled builtin tool IDs for gallery preview",
    )
    model_selection: ModelSelection | None = Field(default=None, description="绑定的模型选择")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")

    model_config = ConfigDict(from_attributes=True)
