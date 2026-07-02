"""Agent统一入口模块

提供:
- General Agent - 通用自主决策Agent（基于LangGraph），支持 full/lean/naked/search 多种 prompt 模式
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig
from pydantic import BaseModel, Field

from app.core.types import ChatHistoryReq, MCPServerConfig, ModelConfig

if TYPE_CHECKING:
    from app.ai_agents.general_agent import GeneralAgent

logger = logging.getLogger(__name__)


class BaseAgentParams(BaseModel):
    """基础Agent参数，所有Agent共用的字段

    模型配置说明：
    - model_cfg: 主 Agent 模型，用于推理和决策
    - fallback_model_cfg: 主模型的备用模型（可选），failover 时自动切换
    - lite_model_cfg: 过滤/摘要模型（可选），用于大型工具结果语义过滤和上下文摘要
    - fallback_lite_model_cfg: 过滤模型的备用模型（可选）

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
    safety_fallback_model_cfg: ModelConfig | None = None
    lite_model_cfg: ModelConfig | None = None
    fallback_lite_model_cfg: ModelConfig | None = None
    vision_fallback_model_cfg: ModelConfig | None = None
    search_service_cfg: SearchServiceConfig | None = None
    mcp_cfg: list[MCPServerConfig] | None = None
    user_instructions: str | None = None
    fetch_raw_webpage: bool = False
    timezone: str | None = None
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
    memory_require_confirmation: bool = False
    enable_memory_auto_extraction: bool = True
    incognito_mode: bool = False
    enable_advanced_retrieval: bool = False
    embedding_config: EmbeddingConfig | None = None
    reranker_config: RerankerConfig | None = None
    enable_render_ui: bool = False
    enable_browser: bool = False
    browser_engine: str | None = None
    browser_source: str | None = None
    dialog_policy: str | None = None
    session_recording: str | None = None
    enable_computer_use: bool = False
    enable_file_ops: bool = True
    enable_code_execute: bool = True
    enable_wiki: bool = False
    enable_kanban: bool = False
    enable_canvas: bool = False
    canvas_id: str | None = None
    enable_answer_tool: bool = False
    enable_planning: bool = False
    kanban_tool_mode: str = "orchestrator"
    kanban_current_task_id: str | None = None
    kanban_max_runtime_seconds: int | None = None
    kanban_zombie_timeout_seconds: int = 120
    unattended_mode: bool = False
    auto_restore_domains: list[str] = []
    enable_web_search: bool = True
    agent_skill_ids: list[str] = []
    agent_skill_configs: dict[str, dict] | None = None
    security_config_raw: dict[str, object] | None = None
    agent_security_raw: dict[str, object] | None = None
    channel_name: str = "web_chat"
    memory_channel_id: str | None = None
    memory_conversation_id: str | None = None
    memory_task_id: str | None = None
    memory_shared_context_ids: list[str] = []
    declared_capabilities: tuple[str, ...] = ()
    declared_allowed_roots: tuple[str, ...] = ()
    external_agents_config: list[dict[str, object]] | None = None
    force_delegate_agent: str | None = None
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
    max_iterations: int | None = None
    memory_policy: AgentMemoryPolicy | None = None
    memory_decay_profile: str | None = None
    engine_params: dict[str, object] | None = None
    jit_subagents: dict[str, object] | None = None
    task_adaptive_digest: dict[str, object] | None = None
    goal: dict[str, object] | None = None
    openapi_services: list[dict[str, object]] | None = None
    prompt_mode: str = "full"
    search_depth: str = "normal"
    notify_targets: tuple[dict[str, str], ...] = ()
    tool_gateway_config: dict[str, object] | None = None


class AgentFactory:
    """Agent工厂类，提供统一的Agent创建接口"""

    @classmethod
    def create_general_agent(cls, params: GeneralAgentParams) -> GeneralAgent:
        """创建 General Agent 实例

        创建基于LangGraph的通用Agent，支持完全自主决策

        Args:
            params: General Agent配置

        Returns:
            General Agent实例（GeneralAgent）
        """
        from pathlib import Path

        from myrm_agent_harness.agent.event_log.backends.file_backend import (
            FileEventLogBackend,
        )

        from app.ai_agents.general_agent import GeneralAgent
        from app.config.settings import get_settings

        event_log_backend = None
        if params.event_log_dir and params.chat_id:
            log_dir = Path(params.event_log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            line_max = (
                params.event_log_max_jsonl_line_bytes
                if params.event_log_max_jsonl_line_bytes is not None
                else get_settings().event_log_max_jsonl_line_bytes
            )
            event_log_backend = FileEventLogBackend(
                log_dir=log_dir,
                session_id=params.chat_id,
                max_jsonl_line_bytes=line_max,
            )

        if params.tool_gateway_config:
            from myrm_agent_harness.core.config.gateway import ToolGatewayConfig

            gateway_cfg = ToolGatewayConfig.model_validate(params.tool_gateway_config)
            if params.search_service_cfg:
                params.search_service_cfg.gateway_config = gateway_cfg

            # Inject gateway config into image and video generation params
            if params.image_generation:
                params.image_generation.gateway_config = params.tool_gateway_config
            if params.video_generation:
                params.video_generation.gateway_config = params.tool_gateway_config
            if params.tts:
                params.tts.gateway_config = params.tool_gateway_config

        return GeneralAgent(
            model_cfg=params.model_cfg,
            fallback_model_cfg=params.fallback_model_cfg,
            safety_fallback_model_cfg=params.safety_fallback_model_cfg,
            lite_model_cfg=params.lite_model_cfg,
            fallback_lite_model_cfg=params.fallback_lite_model_cfg,
            vision_fallback_model_cfg=params.vision_fallback_model_cfg,
            mcp_config=params.mcp_cfg,
            search_service_cfg=params.search_service_cfg,
            user_instructions=params.user_instructions,
            chat_id=params.chat_id,
            enable_memory=params.enable_memory,
            memory_require_confirmation=params.memory_require_confirmation,
            enable_memory_auto_extraction=params.enable_memory_auto_extraction,
            incognito_mode=params.incognito_mode,
            enable_advanced_retrieval=params.enable_advanced_retrieval,
            embedding_config=params.embedding_config,
            reranker_config=params.reranker_config,
            enable_render_ui=params.enable_render_ui,
            enable_web_search=params.enable_web_search,
            enable_browser=params.enable_browser,
            enable_computer_use=params.enable_computer_use,
            enable_file_ops=params.enable_file_ops,
            enable_code_execute=params.enable_code_execute,
            enable_wiki=params.enable_wiki,
            enable_kanban=params.enable_kanban,
            enable_canvas=params.enable_canvas,
            canvas_id=params.canvas_id,
            enable_answer_tool=params.enable_answer_tool,
            enable_planning=params.enable_planning,
            kanban_tool_mode=params.kanban_tool_mode,
            kanban_current_task_id=params.kanban_current_task_id,
            kanban_max_runtime_seconds=params.kanban_max_runtime_seconds,
            kanban_zombie_timeout_seconds=params.kanban_zombie_timeout_seconds,
            auto_restore_domains=params.auto_restore_domains,
            skill_ids=params.agent_skill_ids,
            skill_configs=params.agent_skill_configs,
            fetch_raw_webpage=params.fetch_raw_webpage,
            security_config_raw=params.security_config_raw,
            agent_security_raw=params.agent_security_raw,
            channel_name=params.channel_name,
            memory_channel_id=params.memory_channel_id,
            memory_conversation_id=params.memory_conversation_id,
            memory_task_id=params.memory_task_id,
            memory_shared_context_ids=params.memory_shared_context_ids,
            declared_capabilities=params.declared_capabilities,
            declared_allowed_roots=params.declared_allowed_roots,
            external_agents_config=params.external_agents_config,
            image_generation_params=params.image_generation,
            video_generation_params=params.video_generation,
            tts_params=params.tts,
            privacy_enabled=params.privacy_enabled,
            privacy_s2_action=params.privacy_s2_action,
            privacy_s3_action=params.privacy_s3_action,
            privacy_routing_raw=params.privacy_routing_raw,
            privacy_custom_keywords_s2=params.privacy_custom_keywords_s2,
            privacy_custom_keywords_s3=params.privacy_custom_keywords_s3,
            privacy_custom_patterns_s2=params.privacy_custom_patterns_s2,
            privacy_custom_patterns_s3=params.privacy_custom_patterns_s3,
            privacy_sensitive_tools_s2=params.privacy_sensitive_tools_s2,
            privacy_sensitive_tools_s3=params.privacy_sensitive_tools_s3,
            privacy_deep_scan=params.privacy_deep_scan,
            code_execution_allow_network=params.code_execution_allow_network,
            event_log_backend=event_log_backend,
            locale=params.locale,
            agent_id=params.agent_id,
            subagent_ids=params.subagent_ids,
            jit_subagents=params.jit_subagents,
            task_adaptive_digest=params.task_adaptive_digest,
            max_iterations=params.max_iterations,
            memory_policy=params.memory_policy,
            memory_decay_profile=params.memory_decay_profile,
            engine_params=params.engine_params,
            quote=params.quote,
            providers_dict=params.providers_dict,
            light_model_cfg=params.light_model_cfg,
            reasoning_model_cfg=params.reasoning_model_cfg,
            goal=params.goal,
            openapi_services=params.openapi_services,
            prompt_mode=params.prompt_mode,
            search_depth=params.search_depth,
            notify_targets=params.notify_targets,
        )


__all__ = [
    "AgentFactory",
    "BaseAgentParams",
    "GeneralAgentParams",
    "ImageGenerationParams",
    "VideoGenerationParams",
    "TTSParams",
]

GeneralAgentParams.model_rebuild()
