"""Pydantic数据模型"""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from myrm_agent_harness.toolkits.memory.config import (
    MemoryScopeLevel,
    MemoryWritePolicy,
)
from pydantic import BaseModel, Field, model_validator

from app.services.agent.builtin_tool_validation import OptionalBuiltinTools

PersonalityStyleLiteral = Literal[
    # 实用型
    "professional",
    "friendly",
    "concise",
    "detailed",
    "humorous",
    "academic",
    "creative",
    "socratic",
    # 趣味型
    "pirate",
    "shakespeare",
    "noir",
    "kawaii",
    "catgirl",
    "hype",
    "uwu",
    "surfer",
    "wenyan",
]
MemoryDecayProfileLiteral = Literal["permanent", "normal", "fast"]
PromptModeLiteral = Literal["full", "lean", "naked", "search"]
WorkspacePolicyLiteral = Literal[
    "INHERIT_REQUESTER", "ISOLATED_COPY", "READ_ONLY_SANDBOX"
]
AgentTypeLiteral = Literal["individual", "team"]

T = TypeVar("T")


class MessageBase(BaseModel):
    """消息基础模型"""

    role: str = Field(..., description="消息角色：user或assistant")
    content: str = Field(..., description="消息内容")
    metadata: dict[str, Any] | None = Field(None, description="消息元数据")


class MessageDTO(BaseModel):
    """消息领域对象 (Domain Transfer Object)
    用于替代 SQLAlchemy 的 Message 模型，在业务层传递。
    """

    id: str
    chat_id: str
    role: str
    content: str
    sent_at: datetime
    sent_timezone: str
    created_at: datetime
    extra_data: dict[str, Any] | None = None
    sibling_group_id: str | None = None
    is_active: bool = True
    sibling_count: int = 0
    sibling_index: int = 0

    model_config = {"from_attributes": True}


class ChatDTO(BaseModel):
    """聊天会话领域对象 (Domain Transfer Object)
    用于替代 SQLAlchemy 的 Chat 模型，在业务层传递。
    """

    id: str
    agent_id: str | None = None
    title: str | None = None
    first_message: str | None = None
    last_message: str | None = None
    action_mode: str = "fast"
    is_incognito: bool = False
    source: str = "web"
    channel_session_key: str | None = None
    compacted_summary: str | None = None
    compacted_before_id: str | None = None
    compacted_at: datetime | None = None
    compacted_tokens_saved: int | None = None
    session_notes_json: str | None = None
    ephemeral_subagents: dict[str, Any] | None = None
    session_loaded_skill_names: list[str] | None = None
    workspace_dir: str | None = None
    sandbox_base_dir: str | None = None
    project_id: str | None = None
    is_pinned: bool = False
    pin_order: int = 0
    total_calls: int = 0
    total_tokens: int = 0
    total_usd: float = 0.0
    created_at: datetime
    updated_at: datetime
    last_read_at: datetime | None = None
    deleted_at: datetime | None = None
    share_revoked_at: datetime | None = None

    messages: list[MessageDTO] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MessageCreate(MessageBase):
    """创建消息请求模型"""

    messageId: str = Field(..., description="消息ID")
    chatId: str = Field(..., description="聊天会话ID")
    createdAt: datetime | None = Field(None, description="创建时间")

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def handle_extra_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        """将额外字段移动到metadata中"""
        if not isinstance(data, dict):
            return data

        # 定义标准字段
        standard_fields = {
            "messageId",
            "chatId",
            "createdAt",
            "role",
            "content",
            "metadata",
        }

        # 提取额外字段
        extra_fields = {}
        cleaned_data = {}

        for key, value in data.items():
            if key in standard_fields:
                cleaned_data[key] = value
            else:
                extra_fields[key] = value

        # 将额外字段合并到metadata中
        if extra_fields:
            existing_metadata = cleaned_data.get("metadata", {})
            if isinstance(existing_metadata, dict):
                existing_metadata.update(extra_fields)
            else:
                existing_metadata = extra_fields
            cleaned_data["metadata"] = existing_metadata

        return cleaned_data


class MessageResponse(MessageBase):
    """消息响应模型"""

    messageId: str = Field(..., description="消息ID")
    chatId: str = Field(..., description="聊天会话ID")
    createdAt: datetime = Field(..., description="创建时间")
    siblingGroupId: str | None = Field(
        None, description="Sibling group ID for regenerated responses"
    )
    siblingCount: int = Field(0, description="Total siblings in group")
    siblingIndex: int = Field(
        0, description="Current message index in sibling group (1-based)"
    )

    class Config:
        from_attributes = True


class ChatBase(BaseModel):
    """聊天会话基础模型"""

    title: str | None = Field(None, description="聊天标题", max_length=500)
    action_mode: str = Field("fast", description="聊天模式")
    agent_id: str | None = Field(None, description="绑定的智能体 ID")
    ephemeral_subagents: dict[str, Any] | None = Field(
        None, description="JIT 虚拟团队名册"
    )
    workspace_dir: str | None = Field(
        None, description="Per-chat working directory", max_length=1024
    )
    is_incognito: bool = Field(False, description="是否为无痕模式")


class ChatCreate(ChatBase):
    """创建聊天会话请求模型"""

    chat_id: str = Field(..., description="聊天会话ID")
    messages: list[MessageCreate] = Field(default=[], description="消息列表")
    last_message: str | None = Field(None, description="最后一条消息摘要")


class _TitleModelConfig(BaseModel):
    """标题生成的模型配置（从前端 liteModel 映射）"""

    model: str
    api_key: str = Field(alias="apiKey")
    base_url: str | None = Field(None, alias="baseUrl")
    model_kwargs: dict[str, Any] | None = Field(None, alias="modelKwargs")

    model_config = {"populate_by_name": True}


class GenerateTitleRequest(BaseModel):
    """生成标题请求模型

    API Key 不再通过请求传输。后端从 UserConfig 表读取 filter model 配置。
    """

    messages: list[MessageCreate] = Field(..., description="消息列表")

    model_config = {"populate_by_name": True}


class ChatListItem(BaseModel):
    """聊天列表项模型"""

    id: str = Field(..., description="聊天会话ID")
    title: str | None = Field(None, description="聊天标题")
    firstMessage: str | None = Field(None, description="第一条消息")
    lastMessage: str | None = Field(None, description="最后一条消息")
    actionMode: str = Field(..., description="聊天模式")
    source: str = Field(
        default="web", description="来源渠道 (web/whatsapp/telegram/feishu 等)"
    )
    isCompacted: bool = Field(False, description="是否已被压缩")
    isPinned: bool = Field(False, description="是否置顶")
    pinOrder: int = Field(0, description="置顶排序序号 (1-9)")
    projectId: str | None = Field(None, description="所属项目 ID")
    total_calls: int = Field(0, description="Session total model calls")
    total_tokens: int = Field(0, description="Session total tokens")
    total_usd: float = Field(0.0, description="Session total USD cost")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    deletedAt: datetime | None = Field(
        None, description="Soft-delete timestamp (trash)"
    )

    class Config:
        from_attributes = True


class ChatDetail(BaseModel):
    """聊天详情模型"""

    id: str = Field(..., description="聊天会话ID")
    title: str | None = Field(None, description="聊天标题")
    actionMode: str = Field(..., description="聊天模式")
    agent_id: str | None = Field(None, description="绑定的智能体ID")
    is_incognito: bool = Field(False, description="是否为无痕模式")
    compacted_summary: str | None = Field(None, description="上下文压缩结构化摘要")
    compacted_before_id: str | None = Field(None, description="被压缩的最后一条消息ID")
    workspace_dir: str | None = Field(None, description="Per-chat working directory")
    session_loaded_skill_names: list[str] | None = Field(
        None, description="会话级 Skill override 列表"
    )
    total_calls: int = Field(0, description="Session total model calls")
    total_tokens: int = Field(0, description="Session total tokens")
    total_usd: float = Field(0.0, description="Session total USD cost")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class UpdateSummaryRequest(BaseModel):
    """更新摘要请求模型"""

    summary: str = Field(..., description="新的 JSON 结构化摘要", max_length=100000)


class ChatDetailData(BaseModel):
    """聊天详情数据模型（不含消息，消息通过分页端点加载）"""

    chat: ChatDetail = Field(..., description="聊天会话信息")
    message_count: int = Field(..., description="消息总数")


class CursorPage(BaseModel):
    """Cursor-based paginated messages response."""

    messages: list[MessageResponse] = Field(..., description="消息列表（按时间升序）")
    has_more: bool = Field(..., description="是否有更早的消息")
    next_cursor: str | None = Field(None, description="下一页游标（最早一条消息的 ID）")


class UpdateTitleRequest(BaseModel):
    """更新标题请求模型"""

    title: str = Field(..., description="新标题", max_length=500)


class PaginationParams(BaseModel):
    """分页查询参数"""

    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(10, ge=1, le=100, description="每页数量，1-100")


class PaginationMeta(BaseModel):
    """分页元数据"""

    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="总记录数")
    total_pages: int = Field(..., description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模型"""

    items: list[T] = Field(..., description="数据列表")
    pagination: PaginationMeta = Field(..., description="分页信息")


# ============================================================================
# Agent Models
# ============================================================================


class ModelSelection(BaseModel):
    """模型选择引用"""

    providerId: str = Field(..., description="提供商 ID")
    model: str = Field(..., description="模型名称")
    fallbackProviderId: str | None = Field(None, description="备选提供商 ID")
    fallbackModel: str | None = Field(None, description="备选模型名称")
    safetyFallbackProviderId: str | None = Field(None, description="安全备选提供商 ID")
    safetyFallbackModel: str | None = Field(None, description="安全备选模型名称")
    modelKwargs: dict[str, object] | None = Field(
        None, description="模型调用参数 (temperature, top_p, max_tokens 等)"
    )
    routingEnabled: bool | None = Field(
        None, description="Per-agent Smart Routing 开关"
    )
    lightProviderId: str | None = Field(None, description="Per-agent 轻量路由提供商 ID")
    lightModel: str | None = Field(None, description="Per-agent 轻量路由模型")
    reasoningProviderId: str | None = Field(
        None, description="Per-agent 推理路由提供商 ID"
    )
    reasoningModel: str | None = Field(None, description="Per-agent 推理路由模型")


class AgentMemoryPolicyConfig(BaseModel):
    """Agent 记忆读写边界策略。"""

    agent_id: str | None = Field(None, description="Override agent scope identifier")
    channel_id: str | None = Field(
        None, description="Override channel scope identifier"
    )
    conversation_id: str | None = Field(
        None, description="Override conversation scope identifier"
    )
    task_id: str | None = Field(None, description="Override task scope identifier")
    read_scopes: list[MemoryScopeLevel] | None = Field(
        None, description="Visible memory scope levels for recall"
    )
    write_policy: MemoryWritePolicy = Field(
        default=MemoryWritePolicy.INHERIT,
        description="Target scope for new private memories",
    )


SessionResetModeLiteral = Literal["persistent", "daily", "idle"]


class AgentSessionPolicyConfig(BaseModel):
    """Per-agent IM session reset policy override.

    When set on an agent, overrides the user's global sessionPolicy
    from personalSettings for that specific agent.
    """

    mode: SessionResetModeLiteral = Field(
        "daily", description="Session segmentation strategy: persistent | daily | idle"
    )
    daily_reset_hour: int = Field(
        4, description="UTC hour for daily reset (0-23)", ge=0, le=23
    )
    idle_minutes: int = Field(
        120, description="Idle threshold in minutes for idle mode", ge=1, le=10080
    )


class SkillConfig(BaseModel):
    """Skill configuration for a specific agent"""

    is_core: bool = Field(
        False, description="Whether this skill is a core skill (always injected)"
    )


class CommandBindingConfig(BaseModel):
    """Slash command binding to one or more Skills for IM channels."""

    command_name: str = Field(
        ...,
        description="Command name without slash (e.g. 'daily-report')",
        max_length=50,
    )
    skill_ids: list[str] = Field(
        default_factory=list, description="Target Skill IDs (single or bundle)"
    )
    description: str = Field("", description="User-facing description shown in /help")
    aliases: list[str] = Field(
        default_factory=list, description="Alternative command names"
    )
    instruction: str = Field("", description="Ephemeral guidance for bundle execution")

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

    use_gateway: bool = Field(
        default=False, description="Whether to use the Unified Tool Gateway"
    )
    gateway_url: str | None = Field(
        None, description="Base URL of the Unified Tool Gateway"
    )
    auth_token: str | None = Field(
        None, description="Authentication token for the gateway"
    )


class AgentBase(BaseModel):
    """智能体基础模型"""

    name: str = Field(..., description="智能体名称", max_length=255)
    description: str | None = Field(None, description="智能体描述")
    avatar_url: str | None = Field(
        None, description="智能体头像/图标 URL", max_length=500
    )
    home_directory: str | None = Field(
        None, description="Agent Home 目录路径", max_length=500
    )
    is_built_in: bool = Field(False, description="是否为内置 Agent")
    system_prompt: str | None = Field(None, description="系统指令/用户自定义提示词")
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
    mounted_skill_ids: list[str] = Field(
        default=[], description="挂载的其他 Agent 专属技能 ID 列表"
    )
    skill_configs: dict[str, SkillConfig] | None = Field(
        None, description="技能的个性化配置 (如 is_core)"
    )
    enabled_builtin_tools: OptionalBuiltinTools = Field(
        None, description="启用的内置工具 ID 列表"
    )
    browser_source: str | None = Field(
        None,
        description="浏览器获取方式: 'launch'(新建)、'connect'(CDP)、'extension'(扩展桥接)、'auto'(自动)、'remote'(远程)。为空则使用系统默认。",
    )
    dialog_policy: str | None = Field(
        None,
        description="弹窗处理策略: 'smart'(智能)、'auto_accept'(自动确认)、'auto_dismiss'(自动取消)、'wait_for_agent'(等待Agent处理)。为空则使用默认smart。",
    )
    session_recording: str | None = Field(
        None,
        description="浏览器会话录制模式: 'off'(关闭)、'on_failure'(仅失败时保留)、'always'(始终保留)。为空则使用默认off。",
    )
    model_selection: ModelSelection | None = Field(None, description="绑定的模型选择")
    security_overrides: dict[str, object] | None = Field(
        None, description="Per-agent security policy overrides"
    )
    required_capabilities: list[str] = Field(
        default=[],
        description="该 Agent 运行所需的渠道能力列表（如 media, voice_message）",
    )
    prompt_mode: PromptModeLiteral = Field(
        default="full", description="Prompt injection mode: full/lean/naked"
    )
    personality_style: PersonalityStyleLiteral = Field(
        default="professional", description="Personality style preset"
    )
    memory_decay_profile: MemoryDecayProfileLiteral = Field(
        default="normal", description="Memory forgetting decay speed"
    )
    agent_type: AgentTypeLiteral = Field(
        default="individual", description="Agent type: individual or team (leader)"
    )
    allow_discovery: bool = Field(
        default=True, description="是否允许被主Agent通过动态名册发现并委派"
    )
    subagent_ids: list[str] = Field(default=[], description="可委托的子智能体 ID 列表")
    max_iterations: int | None = Field(
        None, description="最大迭代次数（None=使用系统默认值）", ge=5, le=500
    )
    workspace_policy: WorkspacePolicyLiteral = Field(
        default="INHERIT_REQUESTER",
        description="Workspace policy when this agent is used as a delegated subagent",
    )
    memory_policy: AgentMemoryPolicyConfig | None = Field(
        None, description="Agent memory policy"
    )
    session_policy: AgentSessionPolicyConfig | None = Field(
        None,
        description="Per-agent IM session reset policy override (overrides global personalSettings.sessionPolicy)",
    )
    engine_params: dict[str, Any] | None = Field(
        None,
        description="Advanced engine parameters (e.g. max_tool_calls, max_replan_attempts)",
    )
    auto_restore_domains: list[str] = Field(
        default_factory=list,
        description="Hostnames for which the browser toolkit auto-restores persisted login state",
    )
    suggestion_prompts: list[str] | None = Field(
        None,
        description="Custom starter prompts displayed when this agent is active in an empty chat",
    )
    openapi_services: list[dict[str, object]] = Field(
        default_factory=list,
        description="OpenAPI service configurations for zero-code REST API tool integration",
    )
    command_bindings: list[CommandBindingConfig] | None = Field(
        None,
        description="Slash command bindings to Skills for IM channels (e.g. /daily-report -> skill_id)",
    )
    notify_targets: list[dict[str, str]] | None = Field(
        None,
        description="Notification targets for channel_notify_tool [{channel, recipient_id, label?}]",
    )
    tool_gateway_config: ToolGatewayConfigDTO | None = Field(
        None,
        description="Tool Gateway configuration for third-party tools",
    )
    cron_post_run_verify: bool = Field(
        default=False,
        description="Run adversarial delivery verification after unattended cron agent runs (verifier-only, no worker retry)",
    )


class AgentCreate(AgentBase):
    """创建智能体请求模型"""

    pass


class AgentUpdate(BaseModel):
    """更新智能体请求模型"""

    name: str | None = Field(None, description="智能体名称", max_length=255)
    description: str | None = Field(None, description="智能体描述")
    avatar_url: str | None = Field(
        None, description="智能体头像/图标 URL", max_length=500
    )
    home_directory: str | None = Field(
        None, description="Agent Home 目录路径", max_length=500
    )
    is_built_in: bool | None = Field(None, description="是否为内置 Agent")
    system_prompt: str | None = Field(None, description="系统指令/用户自定义提示词")
    mcp_ids: list[str] | None = Field(None, description="关联的 MCP 配置 ID 列表")
    mcp_tool_selections: dict[str, list[str]] | None = Field(
        default=None,
        description="Per-MCP-server tool whitelist: {server_name: [tool_name...]}. None = leave unchanged.",
    )
    skill_ids: list[str] | None = Field(None, description="关联的技能 ID 列表")
    mounted_skill_ids: list[str] | None = Field(
        None, description="挂载的其他 Agent 专属技能 ID 列表"
    )
    skill_configs: dict[str, SkillConfig] | None = Field(
        None, description="技能的个性化配置 (如 is_core)"
    )
    enabled_builtin_tools: OptionalBuiltinTools = Field(
        None, description="启用的内置工具 ID 列表"
    )
    browser_source: str | None = Field(
        None,
        description="浏览器获取方式: 'launch'/'connect'/'extension'/'auto'/'remote'。None=不修改。",
    )
    dialog_policy: str | None = Field(
        None,
        description="弹窗处理策略: 'smart'/'auto_accept'/'auto_dismiss'/'wait_for_agent'。None=不修改。",
    )
    session_recording: str | None = Field(
        None,
        description="浏览器会话录制模式: 'off'/'on_failure'/'always'。None=不修改。",
    )
    model_selection: ModelSelection | None = Field(None, description="绑定的模型选择")
    security_overrides: dict[str, object] | None = Field(
        None, description="Per-agent security policy overrides"
    )
    required_capabilities: list[str] = Field(
        default=[],
        description="该 Agent 运行所需的渠道能力列表（如 media, voice_message）",
    )
    prompt_mode: PromptModeLiteral | None = Field(
        None, description="Prompt injection mode: full/lean/naked"
    )
    personality_style: PersonalityStyleLiteral | None = Field(
        None, description="Personality style preset"
    )
    memory_decay_profile: MemoryDecayProfileLiteral | None = Field(
        None, description="Memory forgetting decay speed"
    )
    agent_type: AgentTypeLiteral | None = Field(
        None, description="Agent type: individual or team (leader)"
    )
    allow_discovery: bool | None = Field(
        None, description="是否允许被主Agent通过动态名册发现并委派"
    )
    subagent_ids: list[str] | None = Field(None, description="可委托的子智能体 ID 列表")
    max_iterations: int | None = Field(
        None, description="最大迭代次数（None=不修改）", ge=5, le=500
    )
    workspace_policy: WorkspacePolicyLiteral | None = Field(
        None,
        description="Workspace policy when this agent is used as a delegated subagent",
    )
    memory_policy: AgentMemoryPolicyConfig | None = Field(
        None, description="Agent memory policy"
    )
    session_policy: AgentSessionPolicyConfig | None = Field(
        None,
        description="Per-agent IM session reset policy override (null = use global policy)",
    )
    engine_params: dict[str, Any] | None = Field(
        None,
        description="Advanced engine parameters (e.g. max_tool_calls, max_replan_attempts)",
    )
    auto_restore_domains: list[str] | None = Field(
        None,
        description=(
            "Browser hostnames for persisted login auto-restore. "
            "Send null or omit the field to leave the stored value unchanged. "
            "Send an empty list [] to clear all configured hostnames."
        ),
    )
    suggestion_prompts: list[str] | None = Field(
        None,
        description="Custom starter prompts displayed when this agent is active in an empty chat",
    )
    openapi_services: list[dict[str, object]] | None = Field(
        None,
        description="OpenAPI service configurations for zero-code REST API tool integration",
    )
    command_bindings: list[CommandBindingConfig] | None = Field(
        None,
        description="Slash command bindings to Skills for IM channels",
    )
    notify_targets: list[dict[str, str]] | None = Field(
        None,
        description="Notification targets for channel_notify_tool [{channel, recipient_id, label?}]",
    )
    tool_gateway_config: ToolGatewayConfigDTO | None = Field(
        None,
        description="Tool Gateway configuration for third-party tools",
    )
    cron_post_run_verify: bool | None = Field(
        None,
        description="Run adversarial delivery verification after unattended cron agent runs",
    )


class AgentResponse(AgentBase):
    """智能体响应模型"""

    id: str = Field(..., description="智能体 ID")
    user_id: str = Field(..., description="用户 ID")
    snapshot_count: int = Field(0, description="可用配置快照数量")
    snapshot_saved: bool | None = Field(
        None,
        description="本次更新是否成功写入变更前快照（仅 PUT 响应）",
    )
    created_at: datetime | None = Field(None, description="创建时间")
    updated_at: datetime | None = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class AgentProfileSnapshotItem(BaseModel):
    """Agent 配置快照列表项"""

    id: str = Field(..., description="快照 ID")
    agent_id: str = Field(..., description="智能体 ID")
    reason: str | None = Field(None, description="快照原因")
    snapshot_data: dict[str, object] = Field(..., description="快照配置数据")
    created_at: datetime = Field(..., description="创建时间")


class AgentListItem(BaseModel):
    """智能体列表项模型"""

    id: str = Field(..., description="智能体 ID")
    name: str = Field(..., description="智能体名称")
    description: str | None = Field(None, description="智能体描述")
    avatar_url: str | None = Field(None, description="智能体头像/图标 URL")
    is_built_in: bool = Field(False, description="是否为内置 Agent")
    agent_type: AgentTypeLiteral = Field(default="individual", description="Agent type")
    prompt_mode: str = Field(
        default="full", description="Prompt mode (full, lean, naked, search)"
    )
    enabled_builtin_tools: list[str] | None = Field(
        None,
        description="Enabled builtin tool IDs for gallery preview",
    )
    model_selection: ModelSelection | None = Field(None, description="绑定的模型选择")
    created_at: datetime | None = Field(None, description="创建时间")
    updated_at: datetime | None = Field(None, description="更新时间")

    class Config:
        from_attributes = True
