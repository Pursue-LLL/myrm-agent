"""[INPUT]
- pydantic / typing (POS: model primitives)

[OUTPUT]
- ChatDTO, ChatBase, ChatCreate, GenerateTitleRequest, _TitleModelConfig, ChatListItem, ChatDetail, ChatDetailData, UpdateSummaryRequest, TurnOutlineItem, UpdateTitleRequest

[POS]
Data transfer objects: chat DTOs, list/detail shapes and chat-level request models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .message import (
    MessageCreate,
    MessageDTO,
)


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
    active_moa_preset_id: str | None = None
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
    session_access_roots: list[dict[str, object]] | None = None
    project_id: str | None = None
    is_pinned: bool = False
    pin_order: int = 0
    tags: list[str] = Field(default_factory=list)
    total_calls: int = 0
    total_tokens: int = 0
    total_usd: float = 0.0
    created_at: datetime
    updated_at: datetime
    last_read_at: datetime | None = None
    deleted_at: datetime | None = None
    share_revoked_at: datetime | None = None
    share_token_fingerprint: str | None = None
    share_revoked_fingerprints: list[str] | None = None
    share_token_expires_at: int | None = None
    share_token_protected: bool | None = None

    messages: list[MessageDTO] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatBase(BaseModel):
    """聊天会话基础模型"""

    title: str | None = Field(default=None, description="聊天标题", max_length=500)
    action_mode: str = Field(default="fast", description="聊天模式")
    agent_id: str | None = Field(default=None, description="绑定的智能体 ID")
    ephemeral_subagents: dict[str, Any] | None = Field(default=None, description="JIT 虚拟团队名册")
    workspace_dir: str | None = Field(default=None, description="Per-chat working directory", max_length=1024)
    is_incognito: bool = Field(default=False, description="是否为无痕模式")


class ChatCreate(ChatBase):
    """创建聊天会话请求模型"""

    chat_id: str = Field(..., description="聊天会话ID")
    messages: list[MessageCreate] = Field(default=[], description="消息列表")
    last_message: str | None = Field(default=None, description="最后一条消息摘要")
    initial_shared_context_ids: list[str] | None = Field(default=None, description="会话初始绑定的共享上下文 IDs")


class GenerateTitleRequest(BaseModel):
    """生成标题请求模型

    API Key 不再通过请求传输。后端从 UserConfig 表读取 filter model 配置。
    """

    messages: list[MessageCreate] = Field(..., description="消息列表")

    model_config = {"populate_by_name": True}


class _TitleModelConfig(BaseModel):
    """标题生成的模型配置（从前端 liteModel 映射）"""

    model: str
    api_key: str = Field(alias="apiKey")
    base_url: str | None = Field(default=None, alias="baseUrl")
    model_kwargs: dict[str, Any] | None = Field(default=None, alias="modelKwargs")

    model_config = {"populate_by_name": True}


class ChatListItem(BaseModel):
    """聊天列表项模型"""

    id: str = Field(..., description="聊天会话ID")
    title: str | None = Field(default=None, description="聊天标题")
    firstMessage: str | None = Field(default=None, description="第一条消息")
    lastMessage: str | None = Field(default=None, description="最后一条消息")
    actionMode: str = Field(..., description="聊天模式")
    source: str = Field(default="web", description="来源渠道 (web/whatsapp/telegram/feishu 等)")
    isCompacted: bool = Field(default=False, description="是否已被压缩")
    isPinned: bool = Field(default=False, description="是否置顶")
    pinOrder: int = Field(default=0, description="置顶排序序号 (1-9)")
    projectId: str | None = Field(default=None, description="所属项目 ID")
    total_calls: int = Field(default=0, description="Session total model calls")
    total_tokens: int = Field(default=0, description="Session total tokens")
    total_usd: float = Field(default=0.0, description="Session total USD cost")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    deletedAt: datetime | None = Field(default=None, description="Soft-delete timestamp (trash)")
    tags: list[str] = Field(default_factory=list, description="会话多维度层级标签列表")

    model_config = ConfigDict(from_attributes=True)


class ChatDetail(BaseModel):
    """聊天详情模型"""

    id: str = Field(..., description="聊天会话ID")
    title: str | None = Field(default=None, description="聊天标题")
    actionMode: str = Field(..., description="聊天模式")
    activeMoaPresetId: str | None = Field(default=None, description="会话 MoA preset（agent 模式 opt-in）")
    agent_id: str | None = Field(default=None, description="绑定的智能体ID")
    is_incognito: bool = Field(default=False, description="是否为无痕模式")
    compacted_summary: str | None = Field(default=None, description="上下文压缩结构化摘要")
    compacted_before_id: str | None = Field(default=None, description="被压缩的最后一条消息ID")
    workspace_dir: str | None = Field(default=None, description="Per-chat working directory")
    session_loaded_skill_names: list[str] | None = Field(default=None, description="会话级 Skill override 列表")
    session_access_roots: list[dict[str, object]] | None = Field(
        default=None,
        description="Session-scoped HITL directory grants (path, writable, source)",
    )
    total_calls: int = Field(default=0, description="Session total model calls")
    total_tokens: int = Field(default=0, description="Session total tokens")
    total_usd: float = Field(default=0.0, description="Session total USD cost")
    tags: list[str] = Field(default_factory=list, description="会话多维度层级标签列表")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)


class ChatDetailData(BaseModel):
    """聊天详情数据模型（不含消息，消息通过分页端点加载）"""

    chat: ChatDetail = Field(..., description="聊天会话信息")
    message_count: int = Field(..., description="消息总数")
    turn_outline: list[TurnOutlineItem] = Field(default_factory=list, description="会话轻量轮次大纲索引")


class UpdateSummaryRequest(BaseModel):
    """更新摘要请求模型"""

    summary: str = Field(..., description="新的 JSON 结构化摘要", max_length=100000)


class TurnOutlineItem(BaseModel):
    """会话轮次大纲轻量投影项（对标 DeepSeek Harness turnOutline 600字节纯 fold 投影）"""

    turn_index: int = Field(..., description="轮次序号（从1开始）")
    user_message_id: str = Field(..., description="本轮用户首条提问消息ID")
    assistant_message_id: str | None = Field(default=None, description="本轮助手最终回复消息ID")
    prompt_preview: str = Field(..., description="用户提问精炼预览（前50字符）")
    reply_preview: str | None = Field(default=None, description="助手回复精炼预览（前120字符）")
    created_at: datetime = Field(..., description="轮次起始时间")
    message_count: int = Field(default=1, description="本轮包含的消息条数")


class UpdateTitleRequest(BaseModel):
    """更新标题请求模型"""

    title: str = Field(..., description="新标题", max_length=500)
