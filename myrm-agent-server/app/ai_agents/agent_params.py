"""[INPUT]
- myrm_agent_harness.agent.meta_tools.mount_policy::FileAccessMode
- myrm_agent_harness.toolkits.memory.config::AgentMemoryPolicy
- myrm_agent_harness.toolkits.retriever.embedding.factory::EmbeddingConfig
- myrm_agent_harness.toolkits.retriever.reranker.factory::RerankerConfig
- myrm_agent_harness.toolkits.web_search::SearchServiceConfig
- app.core.types::ChatHistoryReq, MCPServerConfig, ModelConfig

[OUTPUT]
- BaseAgentParams: 基础 Agent 参数模型
- ImageGenerationParams: 图像生成配置参数模型
- VideoGenerationParams: 视频生成配置参数模型
- TTSParams: 语音合成配置参数模型
- GeneralAgentParams: 通用自主决策 Agent 配置参数模型

[POS]
Agent 参数定义层。从 agents.py 拆分出的纯参数数据结构，
解耦 AgentFactory 创建逻辑与 Pydantic 参数校验，避免单一文件超出行数预算。
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig
from pydantic import BaseModel, Field

from app.core.types import ChatHistoryReq, MCPServerConfig, ModelConfig


class BaseAgentParams(BaseModel):
    """基础Agent参数，所有Agent共用的字段

    模型配置说明：
    - model_cfg: 主 Agent 模型，用于推理和决策
    - fallback_model_cfg: 主模型备用链首节点（可选），failover 时自动切换
    - fallback_model_cfgs: 主模型有序备用链（可选），流式 graph rebuild 逐级 cascade
    - lite_model_cfg: 过滤/摘要模型（可选），用于大型工具结果语义过滤和上下文摘要
    - fallback_lite_model_cfg: 过滤模型备用链首节点（可选）
    - fallback_lite_model_cfgs: lite 模型有序备用链（可选）

    ID 说明：
    - chat_id: 聊天会话标识，用于工作空间隔离（同一聊天共享工作空间）
    - message_id: 消息标识，用于流式事件关联
    """

    message_id: str | None = None
    chat_id: str | None = None
    query: str | list[dict[str, object]] | object
    chat_history: ChatHistoryReq = []
    model_cfg: ModelConfig
    fallback_model_cfg: ModelConfig | None = None
    fallback_model_cfgs: list[ModelConfig] | None = None
    safety_fallback_model_cfg: ModelConfig | None = None
    lite_model_cfg: ModelConfig | None = None
    fallback_lite_model_cfg: ModelConfig | None = None
    fallback_lite_model_cfgs: list[ModelConfig] | None = None
    vision_fallback_model_cfg: ModelConfig | None = None
    vision_fallback_model_cfgs: list[ModelConfig] | None = None
    video_fallback_model_cfgs: list[ModelConfig] | None = None
    search_service_cfg: SearchServiceConfig | None = None
    mcp_cfg: list[MCPServerConfig] | None = None
    user_instructions: str | None = None
    fetch_raw_webpage: bool = False
    timezone: str | None = None
    reasoning_display_mode: Literal["off", "collapsed", "inline"] = "collapsed"
    quote: str | None = None


class ImageGenerationParams(BaseModel):
    """Image generation configuration passed from frontend/config."""

    model: str = "dall-e-3"
    api_key: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    default_size: str = "1024x1024"
    default_quality: str = "standard"
    timeout_seconds: int = 120
    max_retries: int = 1
    gateway_config: dict[str, object] | None = None


class VideoGenerationParams(BaseModel):
    """Video generation configuration passed from frontend/config."""

    provider: str = "openai"
    model: str = "sora"
    api_key: str | None = None
    fallback_providers: list[dict[str, str]] = Field(default_factory=list)
    timeout_seconds: int = 300
    max_retries: int = 1
    default_aspect_ratio: str | None = None
    default_resolution: str | None = None
    default_duration_seconds: int | None = None
    gateway_config: dict[str, object] | None = None


class TTSParams(BaseModel):
    """TTS configuration passed from frontend/config."""

    provider: str = "openai"
    model: str = "tts-1"
    voice: str = "alloy"
    api_key: str | None = None
    timeout_seconds: int = 60
    max_retries: int = 1
    gateway_config: dict[str, object] | None = None


class GeneralAgentParams(BaseAgentParams):
    """General Agent参数"""

    agent_id: str | None = None
    project_id: str | None = None
    subagent_ids: list[str] | None = None
    enable_memory: bool = True
    memory_require_confirmation: bool = True
    enable_memory_auto_extraction: bool = True
    enable_conversation_search: bool = False
    incognito_mode: bool = False
    enable_advanced_retrieval: bool = False
    embedding_config: EmbeddingConfig | None = None
    reranker_config: RerankerConfig | None = None
    enable_structured_clarify: bool = False
    client_surface: str | None = None
    enable_browser: bool = False
    browser_source: str | None = None
    dialog_policy: str | None = None
    session_recording: str | None = None
    enable_computer_use: bool = False
    file_access_mode: FileAccessMode = FileAccessMode.FULL
    enable_shell_tools: bool = True
    enable_wiki: bool = False
    enable_kanban: bool = False
    enable_cron_eager: bool = False
    enable_answer_tool: bool = False
    enable_planning: bool = False
    enable_external_cli: bool = False
    enable_skill_market: bool = False
    enable_skill_manage: bool = False
    force_skill_manage: bool = False
    kanban_tool_mode: str = "orchestrator"
    kanban_default_board_id: str | None = None
    kanban_current_task_id: str | None = None
    kanban_max_runtime_seconds: int | None = None
    kanban_zombie_timeout_seconds: int = 120
    unattended_mode: bool = False
    desktop_preapproved_trust_keys: tuple[str, ...] = ()
    desktop_unattended_fail_fast: bool = False
    auto_restore_domains: list[str] = []
    enable_web_search: bool = True
    web_search_profile_enabled: bool = False
    search_is_user_configured: bool = False
    enable_web_fetch: bool = True
    # Benchmark-only content policy: hosts rejected by web_fetch and substrings
    # rejected in web_search queries. Empty by default so normal product chat
    # is never filtered; only the eval executor sets them for decontamination.
    benchmark_blocked_hostnames: tuple[str, ...] = ()
    benchmark_blocked_terms: tuple[str, ...] = ()
    agent_skill_ids: list[str] = []
    agent_skill_configs: dict[str, dict] | None = None
    security_config_raw: dict[str, object] | None = None
    agent_security_raw: dict[str, object] | None = None
    channel_name: str = "web_chat"
    memory_channel_id: str | None = None
    memory_conversation_id: str | None = None
    memory_task_id: str | None = None
    memory_shared_context_ids: list[str] = []
    memory_shared_context_names: dict[str, str] = {}
    memory_extra_namespaces: list[str] = []
    memory_base_path: str | None = None
    declared_capabilities: tuple[str, ...] = ()
    declared_allowed_roots: tuple[str, ...] = ()
    external_agents_config: list[dict[str, object]] | None = None
    force_external_agent: str | None = None
    image_generation: ImageGenerationParams | None = None
    video_generation: VideoGenerationParams | None = None
    tts: TTSParams | None = None
    privacy_enabled: bool = False
    privacy_s2_action: str = "warn"
    privacy_s3_action: str = "redact"
    privacy_routing_raw: dict[str, object] | None = None
    providers_dict: dict[str, object] | None = None
    light_model_cfg: ModelConfig | None = None
    reasoning_model_cfg: ModelConfig | None = None
    privacy_custom_keywords_s2: list[str] = []
    privacy_custom_keywords_s3: list[str] = []
    privacy_custom_patterns_s2: list[str] = []
    privacy_custom_patterns_s3: list[str] = []
    privacy_sensitive_tools_s2: list[str] = []
    privacy_sensitive_tools_s3: list[str] = []
    privacy_deep_scan: bool = False
    code_execution_allow_network: bool | None = None
    event_log_dir: str | None = None
    # None → app settings event_log_max_jsonl_line_bytes (harness FileEventLogBackend)
    event_log_max_jsonl_line_bytes: int | None = None
    locale: str | None = None
    prompt_locale: str | None = None
    max_iterations: int | None = None
    memory_policy: AgentMemoryPolicy | None = None
    memory_decay_profile: str | None = None
    memory_extraction_preset: str | None = None
    engine_params: dict[str, object] | None = None
    jit_subagents: dict[str, object] | None = None
    session_loaded_skill_names: list[str] | None = None
    session_access_roots: list[dict[str, object]] | None = None
    sandbox_base_dir: str | None = None
    goal: dict[str, object] | None = None
    openapi_services: list[dict[str, object]] | None = None
    prompt_mode: str = "full"
    search_depth: str = "normal"
    notify_targets: tuple[dict[str, str], ...] = ()
    tool_gateway_config: dict[str, object] | None = None
    a2a_enabled: bool = False
    a2a_trusted_peer_ids: list[str] = []


GeneralAgentParams.model_rebuild()

__all__ = [
    "BaseAgentParams",
    "GeneralAgentParams",
    "ImageGenerationParams",
    "TTSParams",
    "VideoGenerationParams",
]
