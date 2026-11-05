"""[INPUT]
- app.services.agent.params.models::AgentRequest, ModelSelection (POS: Agent API request DTO)
- app.core.channel_bridge.config_loader::UserConfigs (POS: decrypted user config bundle)
- app.core.channel_bridge.model_resolver::enrich_model_capabilities, enrich_model_context_window
- app.core.channel_bridge.config_parsers::slot / vision / video fallback chain resolvers

[OUTPUT]
- ModelPlan: every model slot an agent turn runs on, plus the ordered fallback chains
- resolve_model_plan(): resolve request-selected slots and user-config defaults
- finalize_model_plan(): enrich capabilities/context windows and assemble the fallback chains

[POS]
Model slot resolution layer for Agent request conversion. Owns "which model does this turn
use, and what does it fall back to" — independent of routing verdicts and agent profiles.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.types import ModelConfig

from ..models import AgentRequest, ModelSelection

if TYPE_CHECKING:
    from app.core.channel_bridge.config_loader import UserConfigs

logger = logging.getLogger(__name__)

ModelResolver = Callable[[ModelSelection, dict[str, object] | None], Awaitable[ModelConfig]]


@dataclass(slots=True)
class ModelPlan:
    """Resolved model slots for one agent turn.

    Mutated by later stages: specialty/complexity routing replaces ``model_cfg`` and
    ``fallback_model_cfg``; an Agent profile's own model replaces ``model_cfg`` when the
    request carries no explicit selection.
    """

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


async def resolve_model_plan(
    request: AgentRequest,
    configs: UserConfigs | None,
    providers_dict: dict[str, object] | None,
    *,
    resolve: ModelResolver,
) -> ModelPlan:
    """Resolve the primary model and every auxiliary/fallback slot from request + user config."""

    if request.model_selection:
        model_cfg = await resolve(request.model_selection, providers_dict)
    else:
        from app.core.channel_bridge.model_resolver import resolve_model_config

        model_cfg = resolve_model_config(providers_dict)

    if configs and hasattr(configs, "model_cfg") and configs.model_cfg and configs.model_cfg.max_context_tokens is not None:
        model_cfg = model_cfg.model_copy(update={"max_context_tokens": configs.model_cfg.max_context_tokens})

    fallback_model_cfg = None
    if request.fallback_model_selection:
        try:
            fallback_model_cfg = await resolve(request.fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve fallback model, proceeding without it")

    safety_fallback_model_cfg = None
    if request.safety_fallback_model_selection:
        try:
            safety_fallback_model_cfg = await resolve(request.safety_fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve safety fallback model, proceeding without it")

    lite_model_cfg = None
    if request.lite_model_selection:
        try:
            lite_model_cfg = await resolve(request.lite_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve filter model, proceeding without it")

    fallback_lite_model_cfg = None
    if request.fallback_lite_model_selection:
        try:
            fallback_lite_model_cfg = await resolve(request.fallback_lite_model_selection, providers_dict)
        except ValueError:
            pass

    if fallback_model_cfg is None or fallback_lite_model_cfg is None:
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
        )

        config_base_fallback, config_lite_fallback = extract_fallback_model_configs(providers_dict)
        if fallback_model_cfg is None:
            fallback_model_cfg = config_base_fallback
        if fallback_lite_model_cfg is None:
            fallback_lite_model_cfg = config_lite_fallback

    vision_fallback_model_cfg = None
    if request.vision_fallback_model_selection:
        try:
            vision_fallback_model_cfg = await resolve(request.vision_fallback_model_selection, providers_dict)
        except ValueError:
            logger.warning("Failed to resolve vision fallback model, proceeding without it")
    if vision_fallback_model_cfg is None:
        from app.core.channel_bridge.config_parsers import (
            extract_vision_fallback_model_config,
        )

        vision_fallback_model_cfg = extract_vision_fallback_model_config(providers_dict)

    return ModelPlan(
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        safety_fallback_model_cfg=safety_fallback_model_cfg,
        lite_model_cfg=lite_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
    )


def finalize_model_plan(
    request: AgentRequest,
    plan: ModelPlan,
    providers_dict: dict[str, object] | None,
) -> None:
    """Enrich every resolved slot and assemble the ordered fallback chains in place.

    Runs after routing and profile overrides so the enrichment describes the model this turn
    actually uses, not the pre-routing default.
    """

    from app.core.channel_bridge.config_parsers import (
        extract_video_fallback_model_configs,
        resolve_slot_fallback_chain_for_agent,
        resolve_vision_fallback_chain_for_agent,
    )
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    model_cfg = plan.model_cfg
    fallback_model_cfg = plan.fallback_model_cfg
    fallback_lite_model_cfg = plan.fallback_lite_model_cfg
    safety_fallback_model_cfg = plan.safety_fallback_model_cfg
    lite_model_cfg = plan.lite_model_cfg
    vision_fallback_model_cfg = plan.vision_fallback_model_cfg

    selection_vision = request.model_selection.supports_vision if request.model_selection else None
    model_cfg = enrich_model_capabilities(model_cfg, providers_dict, selection_supports_vision=selection_vision)
    model_cfg = enrich_model_context_window(model_cfg, providers_dict)

    default_model_cfg_raw = providers_dict.get("defaultModelConfig") if providers_dict else None
    base_slot = default_model_cfg_raw.get("baseModel") if isinstance(default_model_cfg_raw, dict) else None
    lite_slot = default_model_cfg_raw.get("liteModel") if isinstance(default_model_cfg_raw, dict) else None

    _, base_fallback_cfgs_from_settings = resolve_slot_fallback_chain_for_agent(
        base_slot,
        providers_dict,
        require_tool_calling=True,
    )
    _, lite_fallback_cfgs_from_settings = resolve_slot_fallback_chain_for_agent(
        lite_slot,
        providers_dict,
        require_tool_calling=False,
    )

    fallback_model_cfgs: list[ModelConfig] | None = None
    if base_fallback_cfgs_from_settings:
        fallback_model_cfgs = list(base_fallback_cfgs_from_settings)
    if fallback_model_cfg is not None:
        if fallback_model_cfgs:
            fallback_model_cfgs = [
                fallback_model_cfg,
                *[c for c in fallback_model_cfgs if c.model != fallback_model_cfg.model],
            ]
        else:
            fallback_model_cfgs = [fallback_model_cfg]
    elif fallback_model_cfgs:
        fallback_model_cfg = fallback_model_cfgs[0]

    fallback_lite_model_cfgs: list[ModelConfig] | None = None
    if lite_fallback_cfgs_from_settings:
        fallback_lite_model_cfgs = list(lite_fallback_cfgs_from_settings)
    if fallback_lite_model_cfg is not None:
        if fallback_lite_model_cfgs:
            fallback_lite_model_cfgs = [
                fallback_lite_model_cfg,
                *[c for c in fallback_lite_model_cfgs if c.model != fallback_lite_model_cfg.model],
            ]
        else:
            fallback_lite_model_cfgs = [fallback_lite_model_cfg]
    elif fallback_lite_model_cfgs:
        fallback_lite_model_cfg = fallback_lite_model_cfgs[0]

    if fallback_model_cfg:
        fb_vision = request.fallback_model_selection.supports_vision if request.fallback_model_selection else None
        fallback_model_cfg = enrich_model_capabilities(fallback_model_cfg, providers_dict, selection_supports_vision=fb_vision)
        fallback_model_cfg = enrich_model_context_window(fallback_model_cfg, providers_dict)
    if fallback_lite_model_cfgs:
        enriched_fl_cfgs: list[ModelConfig] = []
        for fl_cfg in fallback_lite_model_cfgs:
            fl_vision = request.fallback_lite_model_selection.supports_vision if request.fallback_lite_model_selection else None
            enriched = enrich_model_capabilities(fl_cfg, providers_dict, selection_supports_vision=fl_vision)
            enriched_fl_cfgs.append(enrich_model_context_window(enriched, providers_dict))
        fallback_lite_model_cfgs = enriched_fl_cfgs
        if fallback_lite_model_cfg is None and enriched_fl_cfgs:
            fallback_lite_model_cfg = enriched_fl_cfgs[0]
    if fallback_model_cfgs:
        enriched_fb_cfgs: list[ModelConfig] = []
        for fb_cfg in fallback_model_cfgs:
            fb_vision = request.fallback_model_selection.supports_vision if request.fallback_model_selection else None
            enriched = enrich_model_capabilities(fb_cfg, providers_dict, selection_supports_vision=fb_vision)
            enriched_fb_cfgs.append(enrich_model_context_window(enriched, providers_dict))
        fallback_model_cfgs = enriched_fb_cfgs
        if fallback_model_cfg is None and enriched_fb_cfgs:
            fallback_model_cfg = enriched_fb_cfgs[0]
    if safety_fallback_model_cfg:
        sf_vision = request.safety_fallback_model_selection.supports_vision if request.safety_fallback_model_selection else None
        safety_fallback_model_cfg = enrich_model_capabilities(
            safety_fallback_model_cfg,
            providers_dict,
            selection_supports_vision=sf_vision,
        )
        safety_fallback_model_cfg = enrich_model_context_window(safety_fallback_model_cfg, providers_dict)
    if lite_model_cfg:
        lite_vision = request.lite_model_selection.supports_vision if request.lite_model_selection else None
        lite_model_cfg = enrich_model_capabilities(lite_model_cfg, providers_dict, selection_supports_vision=lite_vision)
        lite_model_cfg = enrich_model_context_window(lite_model_cfg, providers_dict)
    if fallback_lite_model_cfg:
        fl_vision = request.fallback_lite_model_selection.supports_vision if request.fallback_lite_model_selection else None
        fallback_lite_model_cfg = enrich_model_capabilities(
            fallback_lite_model_cfg,
            providers_dict,
            selection_supports_vision=fl_vision,
        )
        fallback_lite_model_cfg = enrich_model_context_window(fallback_lite_model_cfg, providers_dict)
    if vision_fallback_model_cfg:
        vf_vision = request.vision_fallback_model_selection.supports_vision if request.vision_fallback_model_selection else None
        vision_fallback_model_cfg = enrich_model_capabilities(
            vision_fallback_model_cfg,
            providers_dict,
            selection_supports_vision=vf_vision,
        )
        vision_fallback_model_cfg = enrich_model_context_window(vision_fallback_model_cfg, providers_dict)

    vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
        providers_dict,
        primary_override=vision_fallback_model_cfg,
        main_model_cfg=model_cfg if model_cfg.supports_vision else None,
    )

    video_fallback_cfgs = extract_video_fallback_model_configs(providers_dict)

    plan.model_cfg = model_cfg
    plan.fallback_model_cfg = fallback_model_cfg
    plan.fallback_model_cfgs = fallback_model_cfgs
    plan.safety_fallback_model_cfg = safety_fallback_model_cfg
    plan.lite_model_cfg = lite_model_cfg
    plan.fallback_lite_model_cfg = fallback_lite_model_cfg
    plan.fallback_lite_model_cfgs = fallback_lite_model_cfgs
    plan.vision_fallback_model_cfg = vision_fallback_model_cfg
    plan.vision_fallback_model_cfgs = vision_fallback_model_cfgs
    plan.video_fallback_model_cfgs = video_fallback_cfgs if video_fallback_cfgs else None
