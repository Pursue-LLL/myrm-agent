"""Resolve extraction LLMs for a chat using the same path as GeneralAgent factory.

[INPUT]
app.services.chat.chat_service::ChatService (POS: chat metadata)
app.ai_agents.general_agent.llm_factory::create_agent_llms (POS: LLM 实例工厂)
app.ai_agents.general_agent.llm_factory::apply_lite_context_downgrade (POS: Dynamic Ratio Shield)
app.services.agent.profile.profile_resolver::AgentProfileResolver (POS: 统一智能体配置解析服务)

[OUTPUT]
resolve_chat_extraction_llm: Returns (main_llm, extraction_llm) aligned with auto-extract.

[POS]
Business-layer SSOT for manual memory extract retry. Mirrors factory lite LLM resolution
(chat agent main model + user lite model + context downgrade) without building GeneralAgent.
Per-turn privacy_routing is not replayed (requires live AgentRequest).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


async def _resolve_main_model_cfg(
    agent_id: str | None,
    providers_dict: dict[str, object] | None,
    configs: object | None,
) -> "ModelConfig":
    from app.core.channel_bridge.model_resolver import resolve_model_config

    model_cfg = resolve_model_config(providers_dict)
    if (
        configs
        and hasattr(configs, "model_cfg")
        and configs.model_cfg
        and configs.model_cfg.max_context_tokens is not None
    ):
        model_cfg = model_cfg.model_copy(
            update={"max_context_tokens": configs.model_cfg.max_context_tokens}
        )

    if not agent_id:
        return model_cfg

    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    resolved = await get_agent_profile_resolver().resolve(agent_id)
    if resolved is None or not resolved.model:
        return model_cfg

    if resolved.model_kwargs:
        from app.services.agent.params.models import ModelSelection
        from app.services.agent.params.resolvers import _resolve_model_config

        agent_model_selection = ModelSelection(
            provider_id="auto",
            model=resolved.model,
            model_kwargs=resolved.model_kwargs,
        )
        try:
            return await _resolve_model_config(agent_model_selection, providers_dict)
        except Exception:
            logger.warning(
                "Failed to resolve agent model '%s' with kwargs for chat extraction, keeping default",
                resolved.model,
            )
            return model_cfg

    from app.core.channel_bridge.model_resolver import (
        resolve_model_config as _resolve_override_model,
    )

    try:
        return _resolve_override_model(providers_dict, model_override=resolved.model)
    except Exception:
        logger.warning(
            "Failed to resolve agent model '%s' for chat extraction, keeping default",
            resolved.model,
        )
        return model_cfg


async def _resolve_lite_model_cfg(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    if not providers_dict:
        return None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None

    lite_model = default_model_cfg.get("liteModel")
    if not isinstance(lite_model, dict):
        return None

    selection = lite_model.get("primary") or lite_model.get("selection")
    if not isinstance(selection, dict):
        return None

    provider_id = selection.get("providerId")
    model = selection.get("model")
    if not provider_id or not model:
        return None

    raw_kwargs = lite_model.get("modelKwargs")
    model_kwargs = raw_kwargs if isinstance(raw_kwargs, dict) else None

    from app.services.agent.params.models import ModelSelection
    from app.services.agent.params.resolvers import _resolve_model_config

    lite_selection = ModelSelection(
        provider_id=str(provider_id),
        model=str(model),
        model_kwargs=model_kwargs,
    )
    try:
        return await _resolve_model_config(lite_selection, providers_dict)
    except ValueError:
        logger.warning(
            "Failed to resolve lite model for chat extraction, proceeding without it"
        )
        return None


async def resolve_chat_extraction_llm(
    chat_id: str,
) -> tuple["BaseChatModel", "BaseChatModel"]:
    """Resolve main and extraction LLMs for a chat (factory-aligned SSOT)."""
    from app.ai_agents.general_agent.llm_factory import (
        apply_lite_context_downgrade,
        create_agent_llms,
    )
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import enrich_model_context_window
    from app.services.chat.chat_service import ChatService

    resolved_chat_id = chat_id.strip()
    if not resolved_chat_id:
        raise ValueError("Chat id is required")

    chat = await ChatService.get_chat_metadata(resolved_chat_id)
    if chat is None:
        raise ValueError("Chat not found")

    configs = await load_user_configs()
    providers_dict = configs.providers_dict if configs else None

    model_cfg = await _resolve_main_model_cfg(chat.agent_id, providers_dict, configs)
    lite_model_cfg = await _resolve_lite_model_cfg(providers_dict)

    model_cfg = enrich_model_context_window(model_cfg, providers_dict)
    if lite_model_cfg is not None:
        lite_model_cfg = enrich_model_context_window(lite_model_cfg, providers_dict)

    llm, lite_llm, _, _ = await create_agent_llms(
        model_cfg,
        lite_model_cfg,
        None,
        None,
    )
    lite_llm, _effective_lite_cfg = await apply_lite_context_downgrade(
        llm, lite_llm, model_cfg, lite_model_cfg
    )
    return llm, lite_llm
