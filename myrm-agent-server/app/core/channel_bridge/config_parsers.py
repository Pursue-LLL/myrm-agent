from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.types import SessionPolicy, SessionResetMode, TTSMode
from app.core.channel_bridge.model_resolver import _to_litellm_model

"""Configuration parsers for various config types.

Extract typed configs from frontend dict structures.

[INPUT]
- retrieval_dict, mcp_dict, voice_dict, providers_dict, personal_settings_dict, search_services_dict

[OUTPUT]
- extract_* functions: parse frontend config to typed objects
- build_vision_fallback_config_chain / resolve_vision_fallback_chain_for_agent: ordered vision auxiliary provider chain
- build_vision_fallback_engine_from_providers: build harness VisionFallbackEngine from WebUI settings
- extract_web_tts_config: Web read-aloud TTS config (ignores channel ttsMode gate)
- session_policy_from_agent_dict: build SessionPolicy from per-agent metadata dict
- is_search_user_configured: check if user explicitly configured a search service (vs default fallback)
- extract_search_provider_chain: enabled search configs sorted by priority → harness SearchServiceConfig list
- extract_active_search_config: head provider + full provider_chain for agent runtime
- verify_search_service_available: async live probe for chain head (30s TTL cache via search_verify)
- invalidate_search_health_cache: clear search health cache on config change
"""

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import VisionFallbackEngine
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.channels.types import VoiceConfig
    from app.core.types import MCPServerConfig, ModelConfig

logger = logging.getLogger(__name__)


def _int_setting(val: object, default: int) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val, 10)
        except ValueError:
            return default
    return default


_PROVIDER_API_BASES: dict[str, str] = {
    "siliconflow": "https://api.siliconflow.cn/v1",
}

_DEFAULT_SESSION_POLICY = SessionPolicy()


def extract_retrieval_models(
    retrieval_dict: dict[str, object] | None,
) -> tuple["EmbeddingConfig | None", "RerankerConfig | None"]:
    """Extract EmbeddingConfig and RerankerConfig from the frontend's retrieval config.

    Only returns configs where applied=True and apiKey is present.
    Converts provider+model to LiteLLM format and fills in default API bases.
    """
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    if not retrieval_dict:
        return None, None

    embedding_cfg = _build_embedding_config(retrieval_dict, EmbeddingConfig)
    reranker_cfg = _build_reranker_config(retrieval_dict, RerankerConfig)
    return embedding_cfg, reranker_cfg


def extract_mcp_configs(mcp_dict: dict[str, object] | None) -> list["MCPServerConfig"]:
    """Extract enabled MCP server configs from the frontend's mcpServers config."""
    from app.core.types import MCPServerConfig

    if not mcp_dict:
        return []

    raw_configs = mcp_dict.get("mcpConfigs")
    if not isinstance(raw_configs, list):
        return []

    result: list[MCPServerConfig] = []
    for cfg in raw_configs:
        if not isinstance(cfg, dict) or not cfg.get("enabled"):
            continue
        try:
            result.append(MCPServerConfig.model_validate(cfg))
        except Exception as e:
            logger.warning(
                "config_parsers: skipping invalid MCP config '%s': %s",
                cfg.get("name", "?"),
                e,
            )

    return result


def extract_org_mcp_configs(
    org_mcp_dict: dict[str, object] | None,
) -> list["MCPServerConfig"]:
    """Extract org-managed MCP server configs pushed by the Control Plane.

    Org MCPs are read-only and always available to every agent; the runtime merge
    in converter.py appends them to the user config and tags them with
    ``extra_params.scope == "org"``. Structure mirrors the frontend
    ``orgMcpServers`` config: ``{"servers": [...]}``.
    """
    from app.core.types import MCPServerConfig

    if not org_mcp_dict:
        return []

    raw_servers = org_mcp_dict.get("servers")
    if not isinstance(raw_servers, list):
        return []

    result: list[MCPServerConfig] = []
    for raw in raw_servers:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        cfg = {
            **raw,
            "extra_params": {**(raw.get("extra_params") or {}), "scope": "org"},
        }
        try:
            result.append(MCPServerConfig.model_validate(cfg))
        except Exception as e:
            logger.warning(
                "config_parsers: skipping invalid org MCP config '%s': %s",
                raw.get("name", "?"),
                e,
            )

    return result


def _build_voice_config_from_dict(voice_dict: dict[str, object]) -> "VoiceConfig":
    """Build VoiceConfig from the frontend voice settings dict."""
    from app.channels.types import VoiceConfig

    stt_enabled = bool(voice_dict.get("sttEnabled", False))
    tts_mode_raw = str(voice_dict.get("ttsMode", "off")).lower()
    tts_mode = (
        TTSMode(tts_mode_raw)
        if tts_mode_raw in ("off", "always", "inbound")
        else TTSMode.OFF
    )

    return VoiceConfig(
        stt_enabled=stt_enabled,
        stt_provider=str(voice_dict.get("sttProvider", "openai")),
        stt_api_key=str(voice_dict.get("sttApiKey", "")),
        stt_model=str(voice_dict.get("sttModel", "whisper-1")),
        stt_language=(
            voice_dict.get("sttLanguage")
            if isinstance(voice_dict.get("sttLanguage"), str)
            else None
        ),
        stt_local_model=str(voice_dict.get("sttLocalModel", "base")),
        stt_local_device=str(voice_dict.get("sttLocalDevice", "auto")),
        stt_local_compute_type=str(voice_dict.get("sttLocalComputeType", "auto")),
        stt_base_url=str(voice_dict.get("sttBaseUrl", "")),
        tts_mode=tts_mode,
        tts_provider=str(voice_dict.get("ttsProvider", "edge")),
        tts_api_key=str(voice_dict.get("ttsApiKey", "")),
        tts_base_url=str(voice_dict.get("ttsBaseUrl", "")),
        tts_voice=str(voice_dict.get("ttsVoice", "")),
        tts_speed=float(voice_dict.get("ttsSpeed", 1.0)),
        tts_pitch=float(voice_dict.get("ttsPitch", 0.0)),
        tts_max_length=_int_setting(voice_dict.get("ttsMaxLength", 4000), 4000),
        tts_summary_enabled=bool(voice_dict.get("ttsSummaryEnabled", True)),
        tts_summary_threshold=_int_setting(
            voice_dict.get("ttsSummaryThreshold", 1500), 1500
        ),
        tts_summary_model=str(voice_dict.get("ttsSummaryModel", "")),
    )


def extract_voice_config(voice_dict: dict[str, object] | None) -> "VoiceConfig | None":
    """Extract VoiceConfig from the frontend's voice settings.

    Returns None if voice is not configured (STT/TTS both disabled).
    """
    if not voice_dict:
        return None

    built = _build_voice_config_from_dict(voice_dict)
    if not built.stt_enabled and built.tts_mode == TTSMode.OFF:
        return None

    return built


def extract_web_tts_config(
    voice_dict: dict[str, object] | None,
) -> "VoiceConfig | None":
    """Extract VoiceConfig for Web UI read-aloud (/tts API).

    Unlike extract_voice_config, does not require ttsMode != off or sttEnabled.
    Channel outbound TTS still uses extract_voice_config.
    """
    if not voice_dict:
        return None
    return _build_voice_config_from_dict(voice_dict)


def extract_lite_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Extract the filter/summary model config from the frontend's providers config."""
    from app.core.types import ModelConfig

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

    provider_id = str(selection.get("providerId", ""))
    model = str(selection.get("model", ""))
    if not provider_id or not model:
        return None

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return None

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")
        ),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    api_url = str(provider.get("apiUrl", "")) or None

    from app.core.channel_bridge.model_resolver import enrich_model_context_window

    return enrich_model_context_window(
        ModelConfig(model=full_model, api_key=api_key, base_url=api_url),
        providers_dict,
    )


def _model_config_identity(cfg: "ModelConfig") -> tuple[str, str | None]:
    return (cfg.model, cfg.base_url)


def _append_unique_model_config(
    configs: list["ModelConfig"],
    seen: set[tuple[str, str | None]],
    cfg: "ModelConfig | None",
) -> None:
    if cfg is None:
        return
    key = _model_config_identity(cfg)
    if key in seen:
        return
    seen.add(key)
    configs.append(cfg)


def _resolve_vision_fallback_primary_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve visionFallbackModel primary selection to ModelConfig."""
    from app.core.types import ModelConfig

    if not providers_dict:
        return None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None

    vision_slot = default_model_cfg.get("visionFallbackModel")
    if not isinstance(vision_slot, dict):
        return None

    if "providerId" in vision_slot and "primary" not in vision_slot:
        selection: object = vision_slot
    else:
        selection = vision_slot.get("primary") or vision_slot.get("selection")
    if not isinstance(selection, dict):
        return None

    provider_id = str(selection.get("providerId", ""))
    model = str(selection.get("model", ""))
    if not provider_id or not model:
        return None

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return None

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")
        ),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    api_url = str(provider.get("apiUrl", "")) or None

    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    cfg = ModelConfig(model=full_model, api_key=api_key, base_url=api_url)
    cfg = enrich_model_capabilities(
        cfg,
        providers_dict,
        selection_supports_vision=True,
    )
    return enrich_model_context_window(cfg, providers_dict)


def _resolve_base_primary_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve defaultModelConfig.baseModel.primary without raising."""
    from app.core.types import ModelConfig

    if not providers_dict:
        return None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None

    base_model = default_model_cfg.get("baseModel")
    if not isinstance(base_model, dict):
        return None

    selection = base_model.get("primary") or base_model.get("selection")
    if not isinstance(selection, dict):
        return None

    provider_id = str(selection.get("providerId", ""))
    model = str(selection.get("model", ""))
    if not provider_id or not model:
        return None

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return None

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")
        ),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    api_url = str(provider.get("apiUrl", "")) or None

    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    cfg = ModelConfig(model=full_model, api_key=api_key, base_url=api_url)
    cfg = enrich_model_capabilities(cfg, providers_dict)
    return enrich_model_context_window(cfg, providers_dict)


def build_vision_fallback_config_chain(
    providers_dict: dict[str, object] | None,
    *,
    primary_override: "ModelConfig | None" = None,
    main_model_cfg: "ModelConfig | None" = None,
) -> list["ModelConfig"]:
    """Build ordered vision auxiliary provider chain.

    Order: primary vision fallback → vision slot fallback → vision-capable main agent model.
    """
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    configs: list[ModelConfig] = []
    seen: set[tuple[str, str | None]] = set()

    primary = primary_override or _resolve_vision_fallback_primary_config(providers_dict)
    _append_unique_model_config(configs, seen, primary)

    if providers_dict:
        default_model_cfg = providers_dict.get("defaultModelConfig")
        providers = providers_dict.get("providers")
        if isinstance(default_model_cfg, dict) and isinstance(providers, list):
            vision_slot = default_model_cfg.get("visionFallbackModel")
            slot_fallback = _resolve_slot_fallback(vision_slot, providers)
            if slot_fallback is not None:
                slot_fallback = enrich_model_capabilities(
                    slot_fallback,
                    providers_dict,
                    selection_supports_vision=True,
                )
                slot_fallback = enrich_model_context_window(slot_fallback, providers_dict)
                _append_unique_model_config(configs, seen, slot_fallback)

    main_candidate = main_model_cfg or _resolve_base_primary_model_config(providers_dict)
    if main_candidate is not None and main_candidate.supports_vision:
        _append_unique_model_config(configs, seen, main_candidate)

    return configs


def resolve_vision_fallback_chain_for_agent(
    providers_dict: dict[str, object] | None,
    *,
    primary_override: "ModelConfig | None" = None,
    main_model_cfg: "ModelConfig | None" = None,
) -> tuple["ModelConfig | None", list["ModelConfig"] | None]:
    """Resolve primary cfg and ordered chain for agent runtime injection."""
    cfgs = build_vision_fallback_config_chain(
        providers_dict,
        primary_override=primary_override,
        main_model_cfg=main_model_cfg,
    )
    if not cfgs:
        return None, None
    primary = primary_override or cfgs[0]
    return primary, cfgs


def build_vision_fallback_engine_from_providers(
    providers_dict: dict[str, object] | None,
    *,
    main_model_cfg: "ModelConfig | None" = None,
) -> "VisionFallbackEngine | None":
    """Build VisionFallbackEngine with ordered provider chain from WebUI settings."""
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import create_vision_fallback_engine

    primary, cfgs = resolve_vision_fallback_chain_for_agent(
        providers_dict,
        main_model_cfg=main_model_cfg,
    )
    if not cfgs:
        return None
    return create_vision_fallback_engine(primary, cfgs)


def extract_vision_fallback_model_configs(
    providers_dict: dict[str, object] | None,
) -> list["ModelConfig"]:
    """Extract ordered vision auxiliary provider chain from WebUI settings."""
    return build_vision_fallback_config_chain(providers_dict)


def extract_vision_fallback_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Extract the primary auxiliary vision model from defaultModelConfig.visionFallbackModel."""
    configs = extract_vision_fallback_model_configs(providers_dict)
    return configs[0] if configs else None


def _infer_supports_video(
    model: str,
    providers_dict: dict[str, object] | None,
) -> bool:
    """Infer native video support from custom model info or model id."""
    from app.core.channel_bridge.model_resolver import _lookup_custom_model_info

    custom = _lookup_custom_model_info(model, providers_dict)
    if custom is not None:
        if "supports_video" in custom:
            return bool(custom["supports_video"])
        if "supports_video_input" in custom:
            return bool(custom["supports_video_input"])
    return False


def _resolve_video_fallback_primary_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve videoFallbackModel primary selection to ModelConfig."""
    from app.core.types import ModelConfig

    if not providers_dict:
        return None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None

    video_slot = default_model_cfg.get("videoFallbackModel")
    if not isinstance(video_slot, dict):
        return None

    if "providerId" in video_slot and "primary" not in video_slot:
        selection: object = video_slot
    else:
        selection = video_slot.get("primary") or video_slot.get("selection")
    if not isinstance(selection, dict):
        return None

    provider_id = str(selection.get("providerId", ""))
    model = str(selection.get("model", ""))
    if not provider_id or not model:
        return None

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return None

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")
        ),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    api_url = str(provider.get("apiUrl", "")) or None

    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    cfg = ModelConfig(model=full_model, api_key=api_key, base_url=api_url)
    cfg = enrich_model_capabilities(
        cfg,
        providers_dict,
        selection_supports_vision=True,
    )
    cfg = cfg.model_copy(update={"supports_video": _infer_supports_video(cfg.model, providers_dict)})
    return enrich_model_context_window(cfg, providers_dict)


def build_video_fallback_config_chain(
    providers_dict: dict[str, object] | None,
    *,
    primary_override: "ModelConfig | None" = None,
) -> list["ModelConfig"]:
    """Build ordered video auxiliary provider chain from videoFallbackModel slot."""
    from app.core.channel_bridge.model_resolver import (
        enrich_model_capabilities,
        enrich_model_context_window,
    )

    configs: list[ModelConfig] = []
    seen: set[tuple[str, str | None]] = set()

    primary = primary_override or _resolve_video_fallback_primary_config(providers_dict)
    _append_unique_model_config(configs, seen, primary)

    if providers_dict:
        default_model_cfg = providers_dict.get("defaultModelConfig")
        providers = providers_dict.get("providers")
        if isinstance(default_model_cfg, dict) and isinstance(providers, list):
            video_slot = default_model_cfg.get("videoFallbackModel")
            slot_fallback = _resolve_slot_fallback(video_slot, providers)
            if slot_fallback is not None:
                slot_fallback = enrich_model_capabilities(
                    slot_fallback,
                    providers_dict,
                    selection_supports_vision=True,
                )
                slot_fallback = enrich_model_context_window(slot_fallback, providers_dict)
                slot_fallback = slot_fallback.model_copy(
                    update={"supports_video": _infer_supports_video(slot_fallback.model, providers_dict)}
                )
                _append_unique_model_config(configs, seen, slot_fallback)

    return configs


def extract_video_fallback_model_configs(
    providers_dict: dict[str, object] | None,
) -> list["ModelConfig"]:
    """Extract ordered video auxiliary provider chain from WebUI settings."""
    return build_video_fallback_config_chain(providers_dict)


def extract_video_fallback_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    configs = extract_video_fallback_model_configs(providers_dict)
    return configs[0] if configs else None


def build_video_fallback_probe_engine_from_providers(
    providers_dict: dict[str, object] | None,
) -> object | None:
    """Build a VisionFallbackEngine for the video fallback chain connectivity probe."""
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        create_vision_fallback_engine,
    )

    from app.core.vision.media_router import pick_video_fallback_configs

    video_cfgs = extract_video_fallback_model_configs(providers_dict)
    vision_cfgs = extract_vision_fallback_model_configs(providers_dict)
    chain = pick_video_fallback_configs(video_cfgs, vision_cfgs)
    if not chain:
        return None
    return create_vision_fallback_engine(chain[0], chain)


def extract_user_instructions(
    personal_settings_dict: dict[str, object] | None,
) -> str | None:
    """Extract global user instructions from personalSettings."""
    if not personal_settings_dict:
        return None
    instructions = personal_settings_dict.get("systemInstructions")
    return str(instructions) if instructions else None


def extract_fallback_model_configs(
    providers_dict: dict[str, object] | None,
) -> tuple["ModelConfig | None", "ModelConfig | None"]:
    """Extract fallback model configs for baseModel and liteModel.

    Returns (fallback_model_cfg, fallback_lite_model_cfg).
    """
    if not providers_dict:
        return None, None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None, None

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return None, None

    base_fallback = _resolve_slot_fallback(
        default_model_cfg.get("baseModel"), providers
    )
    lite_fallback = _resolve_slot_fallback(
        default_model_cfg.get("liteModel"), providers
    )

    from app.core.channel_bridge.model_resolver import enrich_model_context_window

    if base_fallback:
        base_fallback = enrich_model_context_window(base_fallback, providers_dict)
    if lite_fallback:
        lite_fallback = enrich_model_context_window(lite_fallback, providers_dict)
    return base_fallback, lite_fallback


def extract_session_policy(
    personal_settings_dict: dict[str, object] | None,
) -> SessionPolicy:
    """Extract IM session reset policy from personalSettings.

    Expected JSON shape in personalSettings:
      { "sessionPolicy": { "mode": "daily", "dailyResetHour": 4, "idleMinutes": 120,
                            "notifyOnReset": true } }

    Returns DEFAULT_SESSION_POLICY when not configured.
    """
    if not personal_settings_dict:
        return _DEFAULT_SESSION_POLICY

    raw = personal_settings_dict.get("sessionPolicy")
    if not isinstance(raw, dict):
        return _DEFAULT_SESSION_POLICY

    try:
        mode = SessionResetMode(str(raw.get("mode", "daily")))
    except ValueError:
        mode = SessionResetMode.DAILY

    daily_hour = raw.get("dailyResetHour")
    idle_minutes = raw.get("idleMinutes")
    notify_raw = raw.get("notifyOnReset")

    return SessionPolicy(
        mode=mode,
        daily_reset_hour=int(daily_hour) if isinstance(daily_hour, (int, float)) else 4,
        idle_minutes=(
            int(idle_minutes) if isinstance(idle_minutes, (int, float)) else 120
        ),
        notify_on_reset=bool(notify_raw) if notify_raw is not None else True,
    )


def session_policy_from_agent_dict(raw: dict[str, object]) -> SessionPolicy:
    """Build a SessionPolicy from a per-agent session_policy dict.

    Accepts the shape stored in agent metadata:
      { "mode": "daily", "daily_reset_hour": 4, "idle_minutes": 120,
        "notify_on_reset": true }
    """
    try:
        mode = SessionResetMode(str(raw.get("mode", "daily")))
    except ValueError:
        mode = SessionResetMode.DAILY

    daily_hour = raw.get("daily_reset_hour")
    idle_min = raw.get("idle_minutes")
    notify_raw = raw.get("notify_on_reset")
    return SessionPolicy(
        mode=mode,
        daily_reset_hour=int(daily_hour) if isinstance(daily_hour, (int, float)) else 4,
        idle_minutes=int(idle_min) if isinstance(idle_min, (int, float)) else 120,
        notify_on_reset=bool(notify_raw) if notify_raw is not None else True,
    )


def is_search_user_configured(search_services_dict: dict[str, object] | None) -> bool:
    """Check whether the user has explicitly configured and enabled a search service."""
    if not search_services_dict:
        return False
    configs = search_services_dict.get("searchServiceConfigs")
    if not isinstance(configs, list) or not configs:
        return False
    return any(isinstance(c, dict) and c.get("enabled") for c in configs)


_search_health_cache: tuple[float, bool] | None = None
_SEARCH_HEALTH_TTL = 30.0


async def verify_search_service_available(cfg: "SearchServiceConfig | None") -> bool:
    """Lightweight connectivity check for the configured search provider chain.

    Uses live search probe with TTL cache (same semantics as Settings verify).
    """
    if cfg is None:
        return False

    from app.services.integrations.search_verify import verify_search_config_cached

    if cfg.provider_chain:
        head = cfg.provider_chain[0]
        return await verify_search_config_cached(head)
    return await verify_search_config_cached(cfg)


async def _ping_searxng(cfg: "SearchServiceConfig") -> bool:
    """HTTP ping SearXNG to verify connectivity."""
    url = cfg.api_base
    if not url:
        logger.warning("Search service check: SearXNG URL not configured")
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code < 500:
                return True
            logger.warning(
                "Search service check: SearXNG returned %d at %s", resp.status_code, url
            )
            return False
    except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
        logger.warning("Search service check: SearXNG unreachable at %s (%s)", url, exc)
        return False
    except Exception as exc:
        logger.warning(
            "Search service check: SearXNG unexpected error at %s (%s)", url, exc
        )
        return False


def invalidate_search_health_cache() -> None:
    """Clear the search service health cache (call after config changes)."""
    global _search_health_cache
    _search_health_cache = None
    from app.services.integrations.search_verify import invalidate_search_verify_cache

    invalidate_search_verify_cache()


def extract_search_provider_chain(
    search_services_dict: dict[str, object] | None,
) -> list["SearchServiceConfig"]:
    """Extract enabled search configs sorted by priority (1 = highest)."""
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.core.integrations.search_catalog.migration import (
        migrate_search_service_configs,
    )
    from app.core.integrations.search_catalog.registry import (
        SearchProviderCatalogRegistry,
    )

    if not search_services_dict:
        return []

    if isinstance(search_services_dict, str):
        import json

        try:
            search_services_dict = json.loads(search_services_dict)
        except Exception:
            return []
    if not isinstance(search_services_dict, dict):
        return []

    configs = search_services_dict.get("searchServiceConfigs")
    if not isinstance(configs, list) or not configs:
        return []

    dict_configs = [c for c in configs if isinstance(c, dict)]
    migrated = migrate_search_service_configs(dict_configs)
    enabled = [c for c in migrated if c.get("enabled")]
    if not enabled:
        return []

    registry = SearchProviderCatalogRegistry.get_instance()
    max_chain = registry.max_chain_size()

    def _priority(row: dict[str, object]) -> int:
        raw = row.get("priority", 999)
        return int(raw) if isinstance(raw, int) else 999

    enabled.sort(key=_priority)
    chain: list[SearchServiceConfig] = []
    for row in enabled[:max_chain]:
        slug = str(row.get("search_service", ""))
        if not registry.is_selectable_slug(slug):
            continue
        chain.append(
            SearchServiceConfig(
                search_service=slug,
                api_key=str(row["api_key"]) if row.get("api_key") else None,
                api_base=str(row["api_base"]) if row.get("api_base") else None,
                extra_params=(
                    row.get("extra_params")
                    if isinstance(row.get("extra_params"), dict)
                    else None
                ),
            )
        )
    return chain


def extract_active_search_config(
    search_services_dict: dict[str, object] | None,
) -> "SearchServiceConfig | None":
    """Extract active search config with priority provider chain attached."""
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    chain = extract_search_provider_chain(search_services_dict)
    if not chain:
        logger.warning(
            "config_parsers: no enabled search provider chain in WebUI Settings"
        )
        return None

    head = chain[0]
    return SearchServiceConfig(
        search_service=head.search_service,
        api_key=head.api_key,
        api_base=head.api_base,
        extra_params=head.extra_params,
        provider_chain=chain,
    )


def _resolve_slot_fallback(
    slot: object,
    providers: list[dict[str, object]],
) -> "ModelConfig | None":
    """Resolve the fallback selection within a ModelSlot to a ModelConfig."""
    from app.core.types import ModelConfig

    if not isinstance(slot, dict):
        return None

    fallback = slot.get("fallback")
    if not isinstance(fallback, dict):
        return None

    provider_id = str(fallback.get("providerId", ""))
    model = str(fallback.get("model", ""))
    if not provider_id or not model:
        return None

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")
        ),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    ptype = str(provider.get("providerType", "")) or None
    full_model = _to_litellm_model(provider_id, model, ptype)
    api_url = str(provider.get("apiUrl", "")) or None
    return ModelConfig(model=full_model, api_key=api_key, base_url=api_url)


def _build_embedding_config(
    retrieval_dict: dict[str, object],
    cls: type["EmbeddingConfig"],
) -> "EmbeddingConfig | None":
    """Build EmbeddingConfig from retrieval dict."""
    params = _parse_retrieval_params(
        retrieval_dict, "embeddingConfig", "embeddingApplied"
    )
    if not params:
        return None
    return cls(model=params[0], api_key=params[1], api_base=params[2])


def _build_reranker_config(
    retrieval_dict: dict[str, object],
    cls: type["RerankerConfig"],
) -> "RerankerConfig | None":
    """Build RerankerConfig from retrieval dict."""
    params = _parse_retrieval_params(
        retrieval_dict, "rerankerConfig", "rerankerApplied"
    )
    if not params:
        return None
    return cls(model=params[0], api_key=params[1], api_base=params[2])


def _parse_retrieval_params(
    retrieval_dict: dict[str, object],
    config_key: str,
    applied_key: str,
) -> tuple[str, str, str | None] | None:
    """Parse model/api_key/api_base from a single retrieval sub-config.

    Returns (model, api_key, api_base) tuple, or None if not applied or incomplete.
    """
    if not retrieval_dict.get(applied_key):
        return None

    raw = retrieval_dict.get(config_key)
    if not isinstance(raw, dict):
        return None

    api_key = raw.get("apiKey")
    if not api_key or not isinstance(api_key, str):
        return None

    provider = str(raw.get("provider", ""))
    model = str(raw.get("model", ""))
    if not model:
        return None

    litellm_model = _to_litellm_model(provider, model)
    api_base = str(raw.get("apiBase") or _PROVIDER_API_BASES.get(provider, "")) or None
    return litellm_model, api_key, api_base


def _extract_active_key(provider: dict[str, object]) -> str | None:
    """Extract active API key from provider dict."""
    if not provider:
        return None

    # Try direct apiKey first
    api_key = provider.get("apiKey")
    if api_key and isinstance(api_key, str):
        return api_key

    # Try keys array
    keys = provider.get("keys")
    if isinstance(keys, list) and len(keys) > 0:
        # Find active key or first key
        active_key = next(
            (k for k in keys if isinstance(k, dict) and k.get("isActive")), keys[0]
        )
        if isinstance(active_key, dict):
            key_val = active_key.get("key")
            if isinstance(key_val, str) and key_val:
                return key_val

    return None
