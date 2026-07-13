"""Channel execution preamble: config, session, agent creation.

[INPUT]
execute_preamble_{types,session,agent,instructions} (POS: preamble 子模块)
app.core.channel_bridge.config_loader (POS: UserConfig 加载)

[OUTPUT]
prepare_channel_execution(): 预算/会话/Agent 创建前置；返回 PrepareChannelExecutionResult（prep 或 pre_events 早退）。

[POS]
渠道 Agent 执行 preamble 编排门面：串联子模块完成 InboundMessage → GeneralAgent。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai_agents.agents import GeneralAgentParams
from app.channels.i18n import get_text
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate, TopicContext
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import (
    extract_fallback_model_configs,
    extract_lite_model_config,
    extract_mcp_configs,
    extract_retrieval_models,
    extract_user_instructions,
)
from app.services.agent.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    ResolvedAgentProfile,
    get_agent_profile_resolver,
)

from .execute_preamble_agent import build_channel_execution_agent
from .execute_preamble_instructions import enrich_channel_user_instructions
from .execute_preamble_session import resolve_channel_session_context
from .execute_preamble_types import ChannelExecutionPrep, PrepareChannelExecutionResult
from .helpers import build_channel_inbound_query
from .session import build_channel_budget_key

if TYPE_CHECKING:
    from .executor import ChannelAgentExecutor

logger = logging.getLogger(__name__)


async def prepare_channel_execution(
    executor: "ChannelAgentExecutor",
    msg: InboundMessage,
    *,
    is_resume: bool,
    topic_context: TopicContext | None,
) -> PrepareChannelExecutionResult:
    pre_events: list[ProgressUpdate | OutboundMessage] = []

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )

    from app.services.budget.enforcer import should_block_execution

    if await should_block_execution():
        logger.warning(
            "Channel execution blocked: daily budget exceeded (block policy), channel=%s chat_id=%s",
            msg.channel,
            msg.chat_id,
        )
        return PrepareChannelExecutionResult(
            pre_events=(
                *pre_events,
                msg.get_or_create_correlation_context().create_reply(
                    content=get_text(msg, "daily_budget_blocked"),
                ),
            ),
        )

    from app.services.budget.channel_budget import should_block_channel

    channel_budget_key = build_channel_budget_key(msg)
    if channel_budget_key and should_block_channel(channel_budget_key):
        logger.warning(
            "Channel execution blocked: channel budget exceeded, channel=%s chat_id=%s sender=%s",
            msg.channel,
            msg.chat_id,
            msg.sender_id,
        )
        return PrepareChannelExecutionResult(
            pre_events=(
                *pre_events,
                msg.get_or_create_correlation_context().create_reply(
                    content=get_text(msg, "channel_budget_blocked"),
                ),
            ),
        )

    configs = await load_user_configs()
    query = build_channel_inbound_query(msg)

    embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)
    memory_settings = configs.personal_settings_dict or {}
    mcp_configs = extract_mcp_configs(configs.mcp_dict)
    lite_model_cfg = extract_lite_model_config(configs.providers_dict)
    fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(configs.providers_dict)
    user_instructions = extract_user_instructions(configs.personal_settings_dict)

    agent_skill_ids: list[str] = []
    agent_subagent_ids: list[str] | None = None
    agent_max_iterations: int | None = None
    resolved_agent_id: str | None = None
    resolved_profile: ResolvedAgentProfile | None = None
    agent_engine_params: dict[str, object] | None = None

    enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    auto_restore_domains: list[str] = []
    memory_decay_profile: str | None = None

    if topic_context and topic_context.agent_id:
        resolved_agent_id = topic_context.agent_id
        resolved_profile = await get_agent_profile_resolver().resolve(topic_context.agent_id)
        if resolved_profile:
            if resolved_profile.system_prompt:
                user_instructions = (
                    f"{user_instructions}\n\n{resolved_profile.system_prompt}"
                    if user_instructions
                    else resolved_profile.system_prompt
                )
            agent_skill_ids = list(resolved_profile.skill_ids)
            agent_subagent_ids = list(resolved_profile.subagent_ids) if resolved_profile.subagent_ids else None
            agent_max_iterations = resolved_profile.max_iterations
            agent_engine_params = resolved_profile.engine_params
            enabled_builtin_tools = list(resolved_profile.enabled_builtin_tools)
            auto_restore_domains = list(resolved_profile.auto_restore_domains)
            raw_decay = resolved_profile.memory_decay_profile
            memory_decay_profile = raw_decay if isinstance(raw_decay, str) else None

    user_instructions = await enrich_channel_user_instructions(
        msg,
        user_instructions=user_instructions,
        resolved_profile=resolved_profile,
        agent_subagent_ids=agent_subagent_ids,
        resolved_agent_id=resolved_agent_id,
    )

    session_ctx = await resolve_channel_session_context(
        executor,
        msg,
        query=query,
        is_resume=is_resume,
        topic_context=topic_context,
        resolved_agent_id=resolved_agent_id,
        resolved_profile=resolved_profile,
        personal_settings_dict=configs.personal_settings_dict,
    )
    pre_events.extend(session_ctx.pre_events)

    agent_outcome = await build_channel_execution_agent(
        msg,
        query=session_ctx.query,
        is_resume=is_resume,
        configs=configs,
        memory_settings=memory_settings,
        embedding_cfg=embedding_cfg,
        reranker_cfg=reranker_cfg,
        mcp_configs=mcp_configs,
        lite_model_cfg=lite_model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        user_instructions=user_instructions,
        chat_id=session_ctx.chat_id,
        session_key=session_ctx.session_key,
        resolved_agent_id=resolved_agent_id,
        resolved_profile=resolved_profile,
        agent_skill_ids=agent_skill_ids,
        agent_subagent_ids=agent_subagent_ids,
        agent_max_iterations=agent_max_iterations,
        agent_engine_params=agent_engine_params,
        enabled_builtin_tools=enabled_builtin_tools,
        auto_restore_domains=auto_restore_domains,
        memory_decay_profile=memory_decay_profile,
    )

    if agent_outcome.early_reply is not None:
        return PrepareChannelExecutionResult(pre_events=(*pre_events, agent_outcome.early_reply))

    agent_result = agent_outcome.result
    if agent_result is None:
        raise RuntimeError("ChannelAgentBuildOutcome must set result or early_reply")

    return PrepareChannelExecutionResult(
        prep=ChannelExecutionPrep(
            agent=agent_result.agent,
            token_ctx=agent_result.token_ctx,
            chat_id=session_ctx.chat_id,
            chat_history=session_ctx.chat_history,
            query_input=agent_result.query_input,
            channel_budget_key=channel_budget_key,
            memory_settings=memory_settings,
            lite_model_cfg=lite_model_cfg,
            session_was_auto_reset=session_ctx.session_was_auto_reset,
            session_policy=session_ctx.session_policy,
            params=agent_result.params,
            agent_engine_params=agent_engine_params,
            user_timezone=str(memory_settings.get("timezone", "")) or None,
        ),
        pre_events=tuple(pre_events),
    )
