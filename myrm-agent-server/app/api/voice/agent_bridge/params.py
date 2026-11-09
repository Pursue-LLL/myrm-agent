"""[INPUT]
- .common (POS: shared types and constants)

[OUTPUT]
- ParamsMixin

[POS]
Voice bridge mixin: build the GeneralAgentParams for a voice turn.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_agents.agents import GeneralAgentParams

from .common import (
    _MAX_TRANSCRIPT_HISTORY,
    _VOICE_SYSTEM_SUFFIX,
    _model_rebuilt,
    logger,
)


class ParamsMixin:
    async def _build_agent_params(self, query: str) -> GeneralAgentParams | None:
        _ensure_model_rebuild()
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
            extract_lite_model_config,
            extract_mcp_configs,
            extract_retrieval_models,
            extract_user_instructions,
            merge_org_mcp_configs,
            resolve_chat_fallback_chains_from_providers,
            resolve_vision_fallback_chain_for_agent,
            verify_search_service_available,
        )
        from app.core.channel_bridge.model_resolver import (
            enrich_model_capabilities,
            enrich_model_context_window,
            resolve_model_config,
        )
        from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

        try:
            configs = await load_user_configs()
        except Exception:
            logger.warning("Voice bridge: failed to load user configs")
            return None

        resolver = get_agent_profile_resolver()
        agent_id = self._agent_id or "builtin-general"
        profile = await resolver.resolve(agent_id)

        if profile and profile.model:
            agent_model_cfg = resolve_model_config(configs.providers_dict, model_override=profile.model)
            agent_model_cfg = enrich_model_capabilities(agent_model_cfg, configs.providers_dict)
            agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)
        else:
            agent_model_cfg = enrich_model_capabilities(configs.model_cfg, configs.providers_dict)
            agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)

        fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(configs.providers_dict)
        fallback_model_cfgs_list, fallback_lite_model_cfgs_list = resolve_chat_fallback_chains_from_providers(
            configs.providers_dict,
            require_tool_calling=True,
        )
        fallback_model_cfgs = fallback_model_cfgs_list or None
        fallback_lite_model_cfgs = fallback_lite_model_cfgs_list or None
        if fallback_model_cfgs and fallback_model_cfg is None:
            fallback_model_cfg = fallback_model_cfgs[0]
        if fallback_lite_model_cfgs and fallback_lite_model_cfg is None:
            fallback_lite_model_cfg = fallback_lite_model_cfgs[0]
        vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
            configs.providers_dict,
            main_model_cfg=(agent_model_cfg if agent_model_cfg.supports_vision else None),
        )
        lite_model_cfg = extract_lite_model_config(configs.providers_dict)
        embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)
        mcp_configs = merge_org_mcp_configs(
            extract_mcp_configs(configs.mcp_dict),
            configs.org_mcp_dict,
        )

        if mcp_configs and profile:
            from app.services.agent.params.mcp_selection import (
                apply_agent_mcp_selection,
            )

            mcp_configs = apply_agent_mcp_selection(
                mcp_configs,
                mcp_ids=profile.mcp_ids or None,
                mcp_tool_selections=profile.mcp_tool_selections or None,
            )

        search_available = await verify_search_service_available(configs.search_cfg)

        user_instructions = extract_user_instructions(configs.personal_settings_dict)

        if profile:
            if profile.system_prompt:
                user_instructions = (
                    f"{user_instructions}\n\n{profile.system_prompt}" if user_instructions else profile.system_prompt
                )
            from app.services.agent.params.response_locale_suffix import (
                apply_response_locale_suffix,
            )

            user_instructions = apply_response_locale_suffix(
                user_instructions,
                engine_params=profile.engine_params,
            )

        voice_instructions = (user_instructions or "") + _VOICE_SYSTEM_SUFFIX

        transcript_ctx = ""
        if self._transcript:
            recent = self._transcript[-_MAX_TRANSCRIPT_HISTORY:]
            lines = [f"{'User' if e.role == 'user' else 'Assistant'}: {e.text}" for e in recent]
            transcript_ctx = "\n\n[Recent voice transcript for context]\n" + "\n".join(lines)

        chat_id = self._chat_id or f"voice-{uuid.uuid4().hex[:12]}"
        message_id = f"vmsg-{uuid.uuid4().hex[:12]}"

        memory_settings = configs.personal_settings_dict or {}

        from app.api.voice.voice_memory_context import voice_memory_context_from
        from app.core.agent.tool_description_locale import resolve_agent_params_locale
        from app.core.security.privacy_settings import privacy_agent_params
        from app.services.agent.profile.profile_resolver import (
            DEFAULT_ENABLED_BUILTIN_TOOLS,
            resolve_builtin_tool_flags,
        )
        from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch
        from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount

        agent_security_raw = (
            {str(k): v for k, v in profile.security_overrides.items()} if profile and profile.security_overrides else None
        )

        skill_ids = list(profile.skill_ids) if profile else []
        subagent_ids = list(profile.subagent_ids) if profile and profile.subagent_ids else None
        enabled_builtin_tools = list(profile.enabled_builtin_tools) if profile else list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        memory_context = voice_memory_context_from(memory_settings, enabled_builtin_tools)

        params = GeneralAgentParams(
            query=query + transcript_ctx,
            model_cfg=agent_model_cfg,
            fallback_model_cfg=fallback_model_cfg,
            fallback_model_cfgs=fallback_model_cfgs,
            lite_model_cfg=lite_model_cfg,
            fallback_lite_model_cfg=fallback_lite_model_cfg,
            fallback_lite_model_cfgs=fallback_lite_model_cfgs,
            vision_fallback_model_cfg=vision_fallback_model_cfg,
            vision_fallback_model_cfgs=vision_fallback_model_cfgs or None,
            search_service_cfg=configs.search_cfg,
            mcp_cfg=mcp_configs or None,
            user_instructions=voice_instructions,
            chat_id=chat_id,
            message_id=message_id,
            agent_id=agent_id,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            enable_memory=memory_context.enable_memory,
            enable_web_search=search_available,
            enable_web_fetch=resolve_enable_web_fetch(agent_security_raw),
            **resolve_agent_mount(
                ExecutionSurface.VOICE,
                resolve_builtin_tool_flags(enabled_builtin_tools),
            ),
            fetch_raw_webpage=bool(memory_settings.get("fetchRawWebpage")),
            enable_memory_auto_extraction=bool(memory_settings.get("enableMemoryAutoExtraction", True)),
            enable_conversation_search=memory_context.enable_conversation_search,
            agent_skill_ids=skill_ids,
            subagent_ids=subagent_ids,
            agent_security_raw=agent_security_raw,
            channel_name="voice_bridge",
            locale=resolve_agent_params_locale(
                personal_settings=memory_settings,
                channel="voice_bridge",
            ),
            providers_dict=configs.providers_dict,
            **privacy_agent_params(memory_settings),
        )

        from app.ai_agents.event_log_injector import (
            inject_event_log_config,
            sanitize_channel_event_log_session_id,
        )

        voice_event_log_sid = sanitize_channel_event_log_session_id(
            chat_id,
            default_prefix="voice",
        )
        inject_event_log_config(params, session_id_override=voice_event_log_sid)
        return params


def _ensure_model_rebuild() -> None:
    """One-time Pydantic model rebuild for forward-ref resolution."""
    global _model_rebuilt  # noqa: PLW0603
    if _model_rebuilt:
        return
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        EmbeddingConfig,
    )
    from myrm_agent_harness.toolkits.retriever.reranker.factory import (
        RerankerConfig,
    )

    from app.ai_agents.agents import GeneralAgentParams

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )
    _model_rebuilt = True
