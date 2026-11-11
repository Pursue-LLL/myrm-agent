"""[INPUT]
- app.core.channel_bridge.config_parsers.common::_append_unique_model_config / _build_enriched_model_config (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)
- app.core.channel_bridge.config_parsers.fallbacks.model::extract_vision_fallback_model_configs (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)
- app.core.channel_bridge.config_parsers.fallbacks.resolution::_resolve_slot_fallback / extract_slot_fallback_chain (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)
- app.core.channel_bridge.model_resolver::_extract_active_key (POS: Aggregate exit of the model resolver package; import path unchanged.)

[OUTPUT]
- _resolve_video_fallback_primary_config: Resolve videoFallbackModel primary selection to ModelConfig.
- build_video_fallback_config_chain: Build ordered video auxiliary provider chain from videoFallbackModel slot.
- extract_video_fallback_model_configs: Extract ordered video auxiliary provider chain from WebUI settings.
- extract_video_fallback_model_config: extract_video_fallback_model_config
- build_video_fallback_probe_engine_from_providers: Build a VisionFallbackEngine for the video fallback chain connectivity probe.
- extract_user_instructions: Extract global user instructions from personalSettings.
- _filter_fallback_chain_for_tool_calling: Drop fallback nodes that explicitly lack function calling (agent-mode safety).
- build_slot_fallback_config_chain: Build ordered ModelConfig chain from a WebUI ModelSlot.
- resolve_slot_fallback_chain_for_agent: Resolve primary cfg and ordered chain for agent runtime injection.
- resolve_chat_fallback_chains_from_providers: Resolve ordered baseModel and liteModel fallback chains from defaultModelConfig.
- extract_fallback_model_configs: Extract primary fallback configs for baseModel and liteModel (chain heads).
- _resolve_slot_primary_config: Resolve the primary selection in a ModelSlot to ModelConfig.
- extract_background_evolution_model_configs: Extract ordered background evolution model chain with 3-tier adaptive fallback.
- extract_background_evolution_model_config: Extract primary background evolution and maintenance model config.

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        VisionFallbackEngine,
    )

    from app.core.types import ModelConfig

from app.core.channel_bridge.config_parsers.common import (
    _append_unique_model_config,
    _build_enriched_model_config,
)
from app.core.channel_bridge.config_parsers.fallbacks.model import extract_vision_fallback_model_configs
from app.core.channel_bridge.config_parsers.fallbacks.resolution import _resolve_slot_fallback, extract_slot_fallback_chain
from app.core.channel_bridge.model_resolver import _extract_active_key

logger = logging.getLogger(__name__)


def _resolve_video_fallback_primary_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve videoFallbackModel primary selection to ModelConfig."""

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
        (p for p in providers if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")),
        None,
    )
    if not provider:
        return None

    api_key = _extract_active_key(provider)
    if not api_key:
        return None

    return _build_enriched_model_config(
        provider_id=provider_id,
        model=model,
        provider=provider,
        providers_dict=providers_dict,
        selection_supports_vision=True,
        infer_video=True,
    )


def build_video_fallback_config_chain(
    providers_dict: dict[str, object] | None,
    *,
    primary_override: "ModelConfig | None" = None,
) -> list["ModelConfig"]:
    """Build ordered video auxiliary provider chain from videoFallbackModel slot."""
    configs: list[ModelConfig] = []
    seen: set[tuple[str, str | None]] = set()

    primary = primary_override or _resolve_video_fallback_primary_config(providers_dict)
    _append_unique_model_config(configs, seen, primary)

    if providers_dict:
        default_model_cfg = providers_dict.get("defaultModelConfig")
        providers = providers_dict.get("providers")
        if isinstance(default_model_cfg, dict) and isinstance(providers, list):
            video_slot = default_model_cfg.get("videoFallbackModel")
            slot_fallback = _resolve_slot_fallback(
                video_slot,
                providers,
                providers_dict=providers_dict,
                selection_supports_vision=True,
                infer_video=True,
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
) -> "VisionFallbackEngine | None":
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


def _filter_fallback_chain_for_tool_calling(
    configs: list["ModelConfig"],
    providers_dict: dict[str, object] | None,
) -> list["ModelConfig"]:
    """Drop fallback nodes that explicitly lack function calling (agent-mode safety)."""
    if not configs or providers_dict is None:
        return configs

    from app.core.channel_bridge.model_resolver import _lookup_custom_model_info

    filtered: list[ModelConfig] = []
    for cfg in configs:
        custom = _lookup_custom_model_info(cfg.model, providers_dict)
        if custom is not None and "supports_function_calling" in custom:
            if not bool(custom["supports_function_calling"]):
                logger.warning(
                    "config_parsers: skipping fallback %s (supports_function_calling=false)",
                    cfg.model,
                )
                continue
        filtered.append(cfg)
    return filtered


def build_slot_fallback_config_chain(
    slot: object,
    providers_dict: dict[str, object] | None,
    *,
    require_tool_calling: bool = False,
) -> list["ModelConfig"]:
    """Build ordered ModelConfig chain from a WebUI ModelSlot."""
    configs = extract_slot_fallback_chain(slot, providers_dict)
    if require_tool_calling:
        configs = _filter_fallback_chain_for_tool_calling(configs, providers_dict)
    return configs


def resolve_slot_fallback_chain_for_agent(
    slot: object,
    providers_dict: dict[str, object] | None,
    *,
    require_tool_calling: bool = False,
) -> tuple["ModelConfig | None", list["ModelConfig"] | None]:
    """Resolve primary cfg and ordered chain for agent runtime injection."""
    cfgs = build_slot_fallback_config_chain(
        slot,
        providers_dict,
        require_tool_calling=require_tool_calling,
    )
    if not cfgs:
        return None, None
    return cfgs[0], cfgs


def resolve_chat_fallback_chains_from_providers(
    providers_dict: dict[str, object] | None,
    *,
    require_tool_calling: bool = False,
) -> tuple[list["ModelConfig"], list["ModelConfig"]]:
    """Resolve ordered baseModel and liteModel fallback chains from defaultModelConfig."""
    if not providers_dict:
        return [], []

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return [], []

    base_cfgs = build_slot_fallback_config_chain(
        default_model_cfg.get("baseModel"),
        providers_dict,
        require_tool_calling=require_tool_calling,
    )
    lite_cfgs = build_slot_fallback_config_chain(
        default_model_cfg.get("liteModel"),
        providers_dict,
        require_tool_calling=False,
    )
    return base_cfgs, lite_cfgs


def extract_fallback_model_configs(
    providers_dict: dict[str, object] | None,
) -> tuple["ModelConfig | None", "ModelConfig | None"]:
    """Extract primary fallback configs for baseModel and liteModel (chain heads).

    Returns (fallback_model_cfg, fallback_lite_model_cfg).
    """
    base_cfgs, lite_cfgs = resolve_chat_fallback_chains_from_providers(providers_dict)
    base_fallback = base_cfgs[0] if base_cfgs else None
    lite_fallback = lite_cfgs[0] if lite_cfgs else None
    return base_fallback, lite_fallback


def _resolve_slot_primary_config(
    slot: object,
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve the primary selection in a ModelSlot to ModelConfig."""
    if not isinstance(slot, dict) or not providers_dict:
        return None

    selection = slot.get("primary") or slot.get("selection")
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
        (p for p in providers if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")),
        None,
    )
    if not provider:
        return None

    return _build_enriched_model_config(
        provider_id=provider_id,
        model=model,
        provider=provider,
        providers_dict=providers_dict,
    )


def extract_background_evolution_model_configs(
    providers_dict: dict[str, object] | None,
) -> list["ModelConfig"]:
    """Extract ordered background evolution model chain with 3-tier adaptive fallback.

    Tier 1: defaultModelConfig.backgroundEvolutionModel (explicit user configuration)
    Tier 2: defaultModelConfig.liteModel (cost-effective lightweight model)
    Tier 3: defaultModelConfig.baseModel (fallback to primary conversation model)
    """
    if not providers_dict:
        return []

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return []

    for slot_key in ("backgroundEvolutionModel", "liteModel", "baseModel"):
        slot = default_model_cfg.get(slot_key)
        if isinstance(slot, dict):
            configs: list[ModelConfig] = []
            seen: set[tuple[str, str | None]] = set()

            primary = _resolve_slot_primary_config(slot, providers_dict)
            _append_unique_model_config(configs, seen, primary)

            fallbacks = extract_slot_fallback_chain(slot, providers_dict)
            for fb in fallbacks:
                _append_unique_model_config(configs, seen, fb)

            if configs:
                return configs

    return []


def extract_background_evolution_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Extract primary background evolution and maintenance model config."""
    configs = extract_background_evolution_model_configs(providers_dict)
    return configs[0] if configs else None
