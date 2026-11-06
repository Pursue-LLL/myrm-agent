"""[INPUT]
- app.core.channel_bridge.config_parsers.fallbacks.model::build_vision_fallback_config_chain / build_vision_fallback_engine_from_providers / extract_lite_model_config / extract_vision_fallback_model_config / extract_vision_fallback_model_configs / resolve_vision_fallback_chain_for_agent (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)
- app.core.channel_bridge.config_parsers.fallbacks.resolution::extract_slot_fallback_chain (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)
- app.core.channel_bridge.config_parsers.fallbacks.slot::build_slot_fallback_config_chain / build_video_fallback_config_chain / build_video_fallback_probe_engine_from_providers / extract_background_evolution_model_config / extract_background_evolution_model_configs / extract_fallback_model_configs / extract_video_fallback_model_config / extract_video_fallback_model_configs / resolve_chat_fallback_chains_from_providers / resolve_slot_fallback_chain_for_agent (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)

[OUTPUT]
- build_vision_fallback_config_chain
- build_vision_fallback_engine_from_providers
- extract_lite_model_config
- extract_vision_fallback_model_config
- extract_vision_fallback_model_configs
- resolve_vision_fallback_chain_for_agent
- extract_slot_fallback_chain
- build_slot_fallback_config_chain
- build_video_fallback_config_chain
- build_video_fallback_probe_engine_from_providers
- extract_background_evolution_model_config
- extract_background_evolution_model_configs
- extract_fallback_model_configs
- extract_video_fallback_model_config
- extract_video_fallback_model_configs
- resolve_chat_fallback_chains_from_providers
- resolve_slot_fallback_chain_for_agent

[POS]
`app.core.channel_bridge.config_parsers.fallbacks` 的唯一入口；各类回退链的解析实现在同目录单独模块中。
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
    extract_video_fallback_model_config,
    extract_video_fallback_model_configs,
    resolve_chat_fallback_chains_from_providers,
    resolve_slot_fallback_chain_for_agent,
)

__all__ = [
    "build_slot_fallback_config_chain",
    "build_video_fallback_config_chain",
    "build_video_fallback_probe_engine_from_providers",
    "build_vision_fallback_config_chain",
    "build_vision_fallback_engine_from_providers",
    "extract_background_evolution_model_config",
    "extract_background_evolution_model_configs",
    "extract_fallback_model_configs",
    "extract_lite_model_config",
    "extract_slot_fallback_chain",
    "extract_video_fallback_model_config",
    "extract_video_fallback_model_configs",
    "extract_vision_fallback_model_config",
    "extract_vision_fallback_model_configs",
    "resolve_chat_fallback_chains_from_providers",
    "resolve_slot_fallback_chain_for_agent",
    "resolve_vision_fallback_chain_for_agent",
]
