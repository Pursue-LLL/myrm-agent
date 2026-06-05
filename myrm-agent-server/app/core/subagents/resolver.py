"""Subagent Model Resolver.

[INPUT]
- myrm_agent_harness.agent.sub_agents.types::ModelResolver (POS: Protocol for resolving a model name string to a BaseChatModel instance.)
- myrm_agent_harness.toolkits.llms.routing.complexity_router::route_task (POS: Task complexity router — two-phase classification with session momentum.)
- app.core.channel_bridge.model_resolver::resolve_model_config (POS: Business-layer model resolution.)

[OUTPUT]
- SubagentModelResolver: Implements ModelResolver protocol to dynamically route subagent tasks to appropriate models based on complexity.

[POS]
Server-layer subagent model resolution. Injects intelligent heterogeneous model routing into the Harness layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from myrm_agent_harness.agent.sub_agents.types import ModelResolver
from myrm_agent_harness.toolkits.llms.routing.complexity_router import RoutingTier, route_task

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


class SubagentModelResolver(ModelResolver):
    """Resolves subagent models dynamically based on task complexity.

    Implements the ModelResolver protocol for the Harness layer.
    When a subagent is spawned, this resolver intercepts the model resolution.
    If an explicit complexity_tier is provided, it uses that.
    Otherwise, it uses the complexity_router to determine the tier based on the task description.
    """

    def __init__(
        self,
        providers_dict: dict[str, Any] | None,
        task_description: str,
        standard_model_cfg: "ModelConfig",
        light_model_cfg: "ModelConfig | None" = None,
        reasoning_model_cfg: "ModelConfig | None" = None,
    ):
        self.providers_dict = providers_dict
        self.task_description = task_description
        self.standard_model_cfg = standard_model_cfg
        self.light_model_cfg = light_model_cfg
        self.reasoning_model_cfg = reasoning_model_cfg

    async def resolve(self, model_name: str, complexity_tier: str | None = None, task_description: str | None = None) -> object:
        """Resolve the model, applying intelligent routing if applicable."""

        from app.core.channel_bridge.model_resolver import resolve_model_config

        # 1. If the user explicitly configured a specific model for this subagent type in YAML,
        # we respect it (unless it's a generic placeholder like "default").
        if model_name and model_name.lower() != "default":
            logger.info(f"[SubagentModelResolver] Using explicitly configured model: {model_name}")
            cfg = resolve_model_config(self.providers_dict, model_override=model_name)
            return self._build_chat_model(cfg)

        # 2. Intelligent Routing
        target_tier = None
        effective_task_desc = task_description or self.task_description

        if complexity_tier:
            try:
                target_tier = RoutingTier(complexity_tier.lower())
                logger.info(f"[SubagentModelResolver] Using explicit complexity_tier: {target_tier.value}")
            except ValueError:
                logger.warning(
                    f"[SubagentModelResolver] Invalid complexity_tier '{complexity_tier}', falling back to auto-routing."
                )

        if not target_tier:
            # Auto-route based on task description
            routing_result = await route_task(
                query=effective_task_desc,
                standard_model_cfg=self.standard_model_cfg,
                light_model_cfg=self.light_model_cfg,
                reasoning_model_cfg=self.reasoning_model_cfg,
            )
            target_tier = routing_result.tier
            logger.info(
                f"[SubagentModelResolver] Auto-routed task to tier: {target_tier.value} (reason: {routing_result.reason})"
            )

        # 3. Select the best config for the tier
        selected_cfg = self.standard_model_cfg
        if target_tier == RoutingTier.SIMPLE and self.light_model_cfg:
            selected_cfg = self.light_model_cfg
        elif target_tier == RoutingTier.REASONING and self.reasoning_model_cfg:
            selected_cfg = self.reasoning_model_cfg

        logger.info(f"[SubagentModelResolver] Final selected model for subagent: {selected_cfg.model}")
        return self._build_chat_model(selected_cfg)

    def _build_chat_model(self, cfg: "ModelConfig") -> "BaseChatModel":
        """Build a LangChain BaseChatModel from a ModelConfig using LiteLLM."""
        from myrm_agent_harness.toolkits.llms import create_litellm_model

        return create_litellm_model(
            model=cfg.model,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            max_tokens=cfg.max_output_tokens or 4096,
            temperature=cfg.temperature or 0.0,
        )
