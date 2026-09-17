"""Agent统一入口模块

提供:
- General Agent - 通用自主决策Agent（基于LangGraph），支持 full/lean/naked/search 多种 prompt 模式
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai_agents.agent_params import (
    BaseAgentParams,
    GeneralAgentParams,
    ImageGenerationParams,
    TTSParams,
    VideoGenerationParams,
)

if TYPE_CHECKING:
    from app.ai_agents.general_agent import GeneralAgent

logger = logging.getLogger(__name__)


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
        from app.core.utils.session_id import is_safe_session_id

        if params.enable_browser and params.prompt_mode != "search":
            from app.services.agent.browser_skill_binding import (
                apply_browser_automation_skill_binding,
            )

            skill_ids, skill_configs = apply_browser_automation_skill_binding(
                list(params.agent_skill_ids),
                params.agent_skill_configs,
                enable_browser=True,
            )
            params.agent_skill_ids = skill_ids
            params.agent_skill_configs = skill_configs

        event_log_backend = None
        if params.event_log_dir and params.chat_id and is_safe_session_id(params.chat_id):
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
            fallback_model_cfgs=params.fallback_model_cfgs,
            safety_fallback_model_cfg=params.safety_fallback_model_cfg,
            lite_model_cfg=params.lite_model_cfg,
            fallback_lite_model_cfg=params.fallback_lite_model_cfg,
            fallback_lite_model_cfgs=params.fallback_lite_model_cfgs,
            vision_fallback_model_cfg=params.vision_fallback_model_cfg,
            vision_fallback_model_cfgs=params.vision_fallback_model_cfgs,
            video_fallback_model_cfgs=params.video_fallback_model_cfgs,
            mcp_config=params.mcp_cfg,
            search_service_cfg=params.search_service_cfg,
            user_instructions=params.user_instructions,
            chat_id=params.chat_id,
            project_id=params.project_id,
            enable_memory=params.enable_memory,
            memory_require_confirmation=params.memory_require_confirmation,
            enable_memory_auto_extraction=params.enable_memory_auto_extraction,
            enable_conversation_search=params.enable_conversation_search,
            incognito_mode=params.incognito_mode,
            enable_advanced_retrieval=params.enable_advanced_retrieval,
            embedding_config=params.embedding_config,
            reranker_config=params.reranker_config,
            enable_structured_clarify=params.enable_structured_clarify,
            client_surface=params.client_surface,
            enable_web_search=params.enable_web_search,
            enable_web_fetch=params.enable_web_fetch,
            benchmark_blocked_hostnames=params.benchmark_blocked_hostnames,
            benchmark_blocked_terms=params.benchmark_blocked_terms,
            enable_browser=params.enable_browser,
            browser_source=params.browser_source,
            dialog_policy=params.dialog_policy,
            session_recording=params.session_recording,
            enable_computer_use=params.enable_computer_use,
            file_access_mode=params.file_access_mode,
            enable_shell_tools=params.enable_shell_tools,
            enable_wiki=params.enable_wiki,
            enable_kanban=params.enable_kanban,
            enable_cron_eager=params.enable_cron_eager,
            enable_answer_tool=params.enable_answer_tool,
            enable_planning=params.enable_planning,
            enable_external_cli=params.enable_external_cli,
            enable_skill_market=params.enable_skill_market,
            enable_skill_manage=params.enable_skill_manage,
            force_skill_manage=params.force_skill_manage,
            kanban_tool_mode=params.kanban_tool_mode,
            kanban_default_board_id=params.kanban_default_board_id,
            kanban_current_task_id=params.kanban_current_task_id,
            kanban_max_runtime_seconds=params.kanban_max_runtime_seconds,
            kanban_zombie_timeout_seconds=params.kanban_zombie_timeout_seconds,
            unattended_mode=params.unattended_mode,
            desktop_preapproved_trust_keys=params.desktop_preapproved_trust_keys,
            desktop_unattended_fail_fast=params.desktop_unattended_fail_fast,
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
            memory_shared_context_names=params.memory_shared_context_names,
            memory_extra_namespaces=params.memory_extra_namespaces,
            memory_base_path=params.memory_base_path,
            declared_capabilities=params.declared_capabilities,
            declared_allowed_roots=params.declared_allowed_roots,
            external_agents_config=params.external_agents_config,
            force_external_agent=params.force_external_agent,
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
            session_loaded_skill_names=params.session_loaded_skill_names,
            sandbox_base_dir=params.sandbox_base_dir,
            max_iterations=params.max_iterations,
            memory_policy=params.memory_policy,
            memory_decay_profile=params.memory_decay_profile,
            memory_extraction_preset=params.memory_extraction_preset,
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
            a2a_enabled=params.a2a_enabled,
            a2a_trusted_peer_ids=params.a2a_trusted_peer_ids,
        )


__all__ = [
    "AgentFactory",
    "BaseAgentParams",
    "GeneralAgentParams",
    "ImageGenerationParams",
    "TTSParams",
    "VideoGenerationParams",
]
