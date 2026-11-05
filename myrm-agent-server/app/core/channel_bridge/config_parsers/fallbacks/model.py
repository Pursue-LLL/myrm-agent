"""轻量模型与视觉回退链解析。

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
    _extract_active_key,
)
from app.core.channel_bridge.config_parsers.fallbacks.resolution import _resolve_slot_fallback

logger = logging.getLogger(__name__)


def extract_lite_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Extract the filter/summary model config from the frontend's providers config.

    Falls back to baseModel / primary model config when liteModel is not configured.
    """
    if not providers_dict:
        return None

    default_model_cfg = providers_dict.get("defaultModelConfig")
    if not isinstance(default_model_cfg, dict):
        return None

    lite_model = default_model_cfg.get("liteModel")
    selection = None
    if isinstance(lite_model, dict):
        selection = lite_model.get("primary") or lite_model.get("selection")

    if not isinstance(selection, dict):
        base_model = default_model_cfg.get("baseModel")
        if isinstance(base_model, dict):
            selection = base_model.get("primary") or base_model.get("selection")
        if not isinstance(selection, dict) and default_model_cfg.get("providerId") and default_model_cfg.get("model"):
            selection = default_model_cfg

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
    )


def _resolve_vision_fallback_primary_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve visionFallbackModel primary selection to ModelConfig."""

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
    )


def _resolve_base_primary_model_config(
    providers_dict: dict[str, object] | None,
) -> "ModelConfig | None":
    """Resolve defaultModelConfig.baseModel.primary without raising."""

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
    )


def build_vision_fallback_config_chain(
    providers_dict: dict[str, object] | None,
    *,
    primary_override: "ModelConfig | None" = None,
    main_model_cfg: "ModelConfig | None" = None,
) -> list["ModelConfig"]:
    """Build ordered vision auxiliary provider chain.

    Order: primary vision fallback → vision slot fallback → vision-capable main agent model.
    """
    configs: list[ModelConfig] = []
    seen: set[tuple[str, str | None]] = set()

    primary = primary_override or _resolve_vision_fallback_primary_config(providers_dict)
    _append_unique_model_config(configs, seen, primary)

    if providers_dict:
        default_model_cfg = providers_dict.get("defaultModelConfig")
        providers = providers_dict.get("providers")
        if isinstance(default_model_cfg, dict) and isinstance(providers, list):
            vision_slot = default_model_cfg.get("visionFallbackModel")
            slot_fallback = _resolve_slot_fallback(
                vision_slot,
                providers,
                providers_dict=providers_dict,
                selection_supports_vision=True,
            )
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
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        create_vision_fallback_engine,
    )

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
