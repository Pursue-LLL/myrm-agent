"""[INPUT]
- myrm_agent_harness.core.security.types::PrivacyRoutingConfig (POS: Foundation layer of the security type hierarchy. All other security modules)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现。管理 Agent 生命周期（初始化、流式执行、资源释放），)
- app.ai_agents.general_agent.config_builders::build_privacy_routing_config / wrap_with_privacy_routing (POS: Config builders for General Agent)
- app.ai_agents.general_agent.llm_factory::apply_lite_managed_fallback / create_agent_llms / apply_lite_context_downgrade (POS: LLM 实例工厂。负责把业务层 `ModelConfig` 转换为可执行的 LangChain 实例。)
- app.services.org_model_policy.enforce::enforce_org_model_policy (POS: Server 业务层 org model policy 执行 SSOT。在 agent build 后校验 primary/fallback/MoA)

[OUTPUT]
- AgentLlmBundle: AgentLlmBundle
- initialize_agent_llms: initialize_agent_llms

[POS]
装配第一阶段；只创建并包装 LLM，不碰工具与中间件。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.core.security.types import PrivacyRoutingConfig

    from app.ai_agents.general_agent.agent import GeneralAgent


@dataclass(slots=True)
class AgentLlmBundle:
    llm: "BaseChatModel"
    fallback_llm: "BaseChatModel | None"
    safety_fallback_llm: "BaseChatModel | None"
    stream_fallback_llms: "list[BaseChatModel] | None"
    lite_llm: "BaseChatModel"
    privacy_routing_cfg: "PrivacyRoutingConfig | None"


async def initialize_agent_llms(agent_wrapper: "GeneralAgent") -> AgentLlmBundle:
    from ..config_builders import build_privacy_routing_config, wrap_with_privacy_routing
    from ..llm_factory import apply_lite_managed_fallback, create_agent_llms

    (
        llm,
        lite_llm,
        fallback_llm,
        safety_fallback_llm,
        stream_fallback_llms,
    ) = await create_agent_llms(
        agent_wrapper.model_cfg,
        agent_wrapper.lite_model_cfg,
        agent_wrapper.fallback_model_cfg,
        agent_wrapper.safety_fallback_model_cfg,
        fallback_model_cfgs=agent_wrapper.fallback_model_cfgs,
    )
    agent_wrapper._lite_llm = lite_llm

    privacy_routing_cfg = build_privacy_routing_config(agent_wrapper.privacy_routing_raw)
    if agent_wrapper._lite_llm is not None:
        from app.ai_agents.general_agent.llm_factory import (
            apply_lite_context_downgrade,
        )

        agent_wrapper._lite_llm, lite_cfg_for_fallback = await apply_lite_context_downgrade(
            llm,
            agent_wrapper._lite_llm,
            agent_wrapper.model_cfg,
            agent_wrapper.lite_model_cfg,
        )
        agent_wrapper._lite_llm = await apply_lite_managed_fallback(
            agent_wrapper._lite_llm,
            lite_cfg_for_fallback,
            agent_wrapper.fallback_lite_model_cfg,
        )

    if privacy_routing_cfg is not None and agent_wrapper._lite_llm is not None:
        agent_wrapper._lite_llm = wrap_with_privacy_routing(agent_wrapper._lite_llm, privacy_routing_cfg)

    from app.services.org_model_policy.enforce import enforce_org_model_policy

    await enforce_org_model_policy(agent_wrapper)

    return AgentLlmBundle(
        llm=llm,
        fallback_llm=fallback_llm,
        safety_fallback_llm=safety_fallback_llm,
        stream_fallback_llms=stream_fallback_llms,
        lite_llm=lite_llm,
        privacy_routing_cfg=privacy_routing_cfg,
    )
