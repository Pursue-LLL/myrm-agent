"""GeneralAgent 的 LLM 初始化：主模型、轻量模型、回退与升级目标。

[POS]
装配第一阶段；只创建并包装 LLM，不碰工具与中间件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.core.security.types import PrivacyRoutingConfig

    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentLlmBundle:
    llm: "BaseChatModel"
    fallback_llm: "BaseChatModel | None"
    safety_fallback_llm: "BaseChatModel | None"
    stream_fallback_llms: "list[BaseChatModel] | None"
    lite_llm: "BaseChatModel"
    escalation_target_llm: "BaseChatModel | None"
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

    escalation_target_llm = None
    if agent_wrapper.reasoning_model_cfg is not None:
        reasoning_model_name = agent_wrapper.reasoning_model_cfg.model
        main_model_name = agent_wrapper.model_cfg.model
        if reasoning_model_name != main_model_name:
            try:
                reasoning_api_keys = getattr(agent_wrapper.reasoning_model_cfg, "api_keys", None)
                from myrm_agent_harness.toolkits.llms import llm_manager

                escalation_target_llm = await llm_manager.get_llm_from_config(
                    agent_wrapper.reasoning_model_cfg, api_keys=reasoning_api_keys
                )
                logger.warning(
                    "Escalation target model: %s (auto-upgrade from %s)",
                    reasoning_model_name,
                    main_model_name,
                )
            except Exception as e:
                logger.warning(
                    "Failed to create escalation target LLM: %s, auto-escalation disabled",
                    e,
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
        escalation_target_llm=escalation_target_llm,
        privacy_routing_cfg=privacy_routing_cfg,
    )
