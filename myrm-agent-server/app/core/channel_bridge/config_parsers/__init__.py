"""配置解析门面。

[INPUT]
app.core.channel_bridge.config_parsers.* (POS: 按配置域拆分的解析函数)

[OUTPUT]
extract_* / build_* / resolve_* / merge_* / session_policy_from_agent_dict / is_search_user_configured /
verify_search_service_available 以及 _build_enriched_model_config（测试与内部调用需要）。

[POS]
channel_bridge 配置解析的唯一公开入口；调用方不需要知道实现位于哪个子模块。
"""

from app.core.channel_bridge.config_parsers.fallbacks.model import (
    build_vision_fallback_config_chain,
    build_vision_fallback_engine_from_providers,
    extract_lite_model_config,
    extract_vision_fallback_model_config,
    extract_vision_fallback_model_configs,
    resolve_vision_fallback_chain_for_agent,
)
from app.core.channel_bridge.config_parsers.fallbacks.resolution import extract_slot_fallback_chain
from app.core.channel_bridge.config_parsers.fallbacks.slot import (
    build_slot_fallback_config_chain,
    build_video_fallback_config_chain,
    build_video_fallback_probe_engine_from_providers,
    extract_background_evolution_model_config,
    extract_background_evolution_model_configs,
    extract_fallback_model_configs,
    extract_user_instructions,
    extract_video_fallback_model_config,
    extract_video_fallback_model_configs,
    resolve_chat_fallback_chains_from_providers,
    resolve_slot_fallback_chain_for_agent,
)
from app.core.channel_bridge.config_parsers.mcp import (
    extract_mcp_configs,
    extract_org_mcp_configs,
    merge_org_mcp_configs,
)
from app.core.channel_bridge.config_parsers.retrieval import extract_retrieval_models
from app.core.channel_bridge.config_parsers.search import (
    extract_active_search_config,
    extract_search_provider_chain,
    is_search_user_configured,
    verify_search_service_available,
)
from app.core.channel_bridge.config_parsers.session import (
    extract_session_policy,
    session_policy_from_agent_dict,
)
from app.core.channel_bridge.config_parsers.voice import (
    extract_voice_config,
    extract_web_tts_config,
)

__all__ = [
    "extract_user_instructions",
    "build_slot_fallback_config_chain",
    "build_video_fallback_config_chain",
    "build_video_fallback_probe_engine_from_providers",
    "build_vision_fallback_config_chain",
    "build_vision_fallback_engine_from_providers",
    "extract_active_search_config",
    "extract_background_evolution_model_config",
    "extract_background_evolution_model_configs",
    "extract_fallback_model_configs",
    "extract_lite_model_config",
    "extract_mcp_configs",
    "extract_org_mcp_configs",
    "extract_retrieval_models",
    "extract_search_provider_chain",
    "extract_session_policy",
    "extract_slot_fallback_chain",
    "extract_video_fallback_model_config",
    "extract_video_fallback_model_configs",
    "extract_vision_fallback_model_config",
    "extract_vision_fallback_model_configs",
    "extract_voice_config",
    "extract_web_tts_config",
    "is_search_user_configured",
    "merge_org_mcp_configs",
    "resolve_chat_fallback_chains_from_providers",
    "resolve_slot_fallback_chain_for_agent",
    "resolve_vision_fallback_chain_for_agent",
    "session_policy_from_agent_dict",
    "verify_search_service_available",
]
