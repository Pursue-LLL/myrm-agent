"""Channel preamble agent assembly: params, factory, resume gate, credentials.

[INPUT]
app.ai_agents.agents::AgentFactory (POS: GeneralAgent 工厂)
app.services.agent.session_credential_assembler (POS: 会话凭证装配)

[OUTPUT]
build_channel_execution_agent(): 创建 GeneralAgent 与 query_input / token_ctx。

[POS]
execute_preamble 子模块：从已解析配置到可运行 Agent 实例的最后一步。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langgraph.types import Command
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.channels.i18n import get_text
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.channel_bridge.config_parsers import verify_search_service_available
from app.core.types.business import ModelConfig
from app.core.types import MCPServerConfig
from app.services.agent.profile_resolver import ResolvedAgentProfile
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

from .execute_preamble_types import build_security_config
from .helpers import _extract_code_exec_network, _resolve_inbound_memory_identity

logger = logging.getLogger(__name__)


@dataclass
class ChannelAgentBuildResult:
    agent: GeneralAgent
    token_ctx: object
    query_input: str | Command[object]
    params: GeneralAgentParams
    pre_events: tuple[ProgressUpdate | OutboundMessage, ...]


async def build_channel_execution_agent(
    msg: InboundMessage,
    *,
    query: str,
    is_resume: bool,
    configs: UserConfigs,
    memory_settings: dict[str, object],
    embedding_cfg: EmbeddingConfig | None,
    reranker_cfg: RerankerConfig | None,
    mcp_configs: list[MCPServerConfig] | None,
    lite_model_cfg: ModelConfig | None,
    fallback_model_cfg: ModelConfig | None,
    fallback_lite_model_cfg: ModelConfig | None,
    user_instructions: str,
    chat_id: str,
    session_key: str,
    resolved_agent_id: str | None,
    resolved_profile: ResolvedAgentProfile | None,
    agent_skill_ids: list[str],
    agent_subagent_ids: list[str] | None,
    agent_max_iterations: int | None,
    agent_engine_params: dict[str, object] | None,
    enabled_builtin_tools: list[str],
    auto_restore_domains: list[str],
    memory_decay_profile: str | None,
) -> ChannelAgentBuildResult | tuple[ProgressUpdate | OutboundMessage, ...]:
    from app.core.memory.proactive.settings import (
        resolve_conversation_search_enabled,
        resolve_memory_enabled,
    )
    from app.services.agent.profile_resolver import (
        apply_agent_baseline_tool_flags,
        resolve_builtin_tool_flags,
    )

    pre_events: list[ProgressUpdate | OutboundMessage] = []

    user_timezone = str(memory_settings.get("timezone", "")) or None
    memory_identity = _resolve_inbound_memory_identity(
        msg,
        fallback_chat_id=chat_id,
        fallback_task_id=session_key,
    )
    memory_shared_context_ids: list[str] = []
    try:
        from app.services.memory.shared_context import resolve_shared_context_ids

        memory_shared_context_ids = await resolve_shared_context_ids(
            agent_id=resolved_agent_id,
            channel_id=memory_identity.channel_id,
            conversation_id=memory_identity.conversation_id,
            task_id=memory_identity.task_id,
        )
    except Exception as e:
        logger.warning(
            "Failed to resolve shared memory contexts for channel message: %s",
            e,
        )

    if resolved_profile and resolved_profile.model:
        from app.core.channel_bridge.model_resolver import (
            enrich_model_context_window,
            resolve_model_config,
        )

        agent_model_cfg = resolve_model_config(
            configs.providers_dict,
            model_override=resolved_profile.model,
        )
        agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)
    else:
        agent_model_cfg = configs.model_cfg

    working_mcp_configs = mcp_configs
    if working_mcp_configs and resolved_profile:
        from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

        working_mcp_configs = apply_agent_mcp_selection(
            working_mcp_configs,
            mcp_ids=resolved_profile.mcp_ids or None,
            mcp_tool_selections=resolved_profile.mcp_tool_selections or None,
        )

    agent_wants_search = "web_search" in enabled_builtin_tools
    search_available = (
        agent_wants_search
        and configs.search_is_user_configured
        and await verify_search_service_available(configs.search_cfg)
    )
    if agent_wants_search and not search_available:
        if not configs.search_is_user_configured:
            err_msg = get_text(msg, "search_not_configured")
        else:
            err_msg = get_text(msg, "search_unreachable")
        return (
            msg.get_or_create_correlation_context().create_reply(content=err_msg),
        )

    from app.ai_agents.general_agent.context import set_current_agent_id, set_current_chat_id, set_current_turn_id

    turn_id = msg.metadata.get("turn_id") or msg.message_id or "unknown"
    set_current_turn_id(turn_id)
    set_current_chat_id(chat_id)
    set_current_agent_id(resolved_agent_id or "default")

    from app.core.channel_bridge.executor_helpers import extract_external_agents

    params = GeneralAgentParams(
        query=query,
        model_cfg=agent_model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        lite_model_cfg=lite_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        search_service_cfg=configs.search_cfg,
        mcp_cfg=working_mcp_configs or None,
        user_instructions=user_instructions,
        chat_id=chat_id,
        agent_id=resolved_agent_id,
        embedding_config=embedding_cfg,
        enable_memory=resolve_memory_enabled(memory_settings),
        reranker_config=reranker_cfg,
        agent_skill_ids=agent_skill_ids,
        subagent_ids=agent_subagent_ids,
        fetch_raw_webpage=bool(memory_settings.get("fetchRawWebpage")),
        enable_web_search=search_available,
        **apply_agent_baseline_tool_flags(resolve_builtin_tool_flags(enabled_builtin_tools)),
        auto_restore_domains=auto_restore_domains,
        enable_advanced_retrieval=bool(
            configs.retrieval_dict.get("enableAdvancedRetrieval") if configs.retrieval_dict else False
        ),
        memory_require_confirmation=bool(memory_settings.get("memoryRequireConfirmation")),
        enable_memory_auto_extraction=bool(memory_settings.get("enableMemoryAutoExtraction")),
        enable_conversation_search=resolve_conversation_search_enabled(memory_settings),
        security_config_raw=build_security_config(configs.security_config_dict, msg.metadata),
        agent_security_raw=(
            {str(k): v for k, v in resolved_profile.security_overrides.items()}
            if resolved_profile and resolved_profile.security_overrides
            else None
        ),
        memory_policy=(resolved_profile.memory_policy if resolved_profile else None),
        memory_decay_profile=memory_decay_profile,
        engine_params=agent_engine_params,
        max_iterations=agent_max_iterations,
        channel_name=msg.channel,
        memory_channel_id=memory_identity.channel_id,
        memory_conversation_id=memory_identity.conversation_id,
        memory_task_id=memory_identity.task_id,
        memory_shared_context_ids=memory_shared_context_ids,
        timezone=user_timezone,
        external_agents_config=extract_external_agents(configs.external_agents_dict),
        code_execution_allow_network=_extract_code_exec_network(memory_settings),
        notify_targets=(resolved_profile.notify_targets if resolved_profile else ()),
    )

    agent = AgentFactory.create_general_agent(params)
    approval_peer = msg.chat_id or msg.sender_id
    agent.approval_session_key = f"{msg.channel}:{approval_peer}"

    query_input: str | Command[object]
    if is_resume:
        approval_key = f"{msg.channel}:{approval_peer}"
        if not ApprovalTimeoutScheduler.get().resolve_if_first(approval_key):
            logger.warning("Channel resume rejected (timeout already resolved): key=%s", approval_key)
            return (
                msg.get_or_create_correlation_context().create_reply(
                    content=get_text(msg, "approval_timeout_resolved"),
                ),
            )
        query_input = Command(resume=msg.resume_value)
    else:
        query_input = query

    from myrm_agent_harness.agent.security import user_credentials_ctx
    from app.services.agent.session_credential_assembler import assemble_session_credentials

    credentials_list = await assemble_session_credentials(
        oauth_credentials_dict=configs.oauth_credentials_dict,
        providers_dict=configs.providers_dict,
        channel=msg.channel,
    )
    token_ctx = user_credentials_ctx.set(credentials_list)
    return ChannelAgentBuildResult(
        agent=agent,
        token_ctx=token_ctx,
        query_input=query_input,
        params=params,
        pre_events=tuple(pre_events),
    )
