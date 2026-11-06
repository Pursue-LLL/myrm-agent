"""[INPUT]
- app.core.channel_bridge.config_parsers.common::_append_unique_model_config / _build_enriched_model_config (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)

[OUTPUT]
- extract_slot_fallback_chain: Resolve the ordered fallback selections within a ModelSlot to ModelConfig list.
- _resolve_slot_fallback: Resolve the primary fallback selection within a ModelSlot to a ModelConfig.

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.types import ModelConfig

from app.core.channel_bridge.config_parsers.common import _append_unique_model_config, _build_enriched_model_config

logger = logging.getLogger(__name__)


def extract_slot_fallback_chain(
    slot: object,
    providers_dict: dict[str, object] | None,
) -> list["ModelConfig"]:
    """Resolve the ordered fallback selections within a ModelSlot to ModelConfig list."""
    if not isinstance(slot, dict) or not providers_dict:
        return []

    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return []

    # Support both list `fallbacks` and legacy single `fallback`
    raw_fallbacks: list[dict[str, object]] = []
    if isinstance(slot.get("fallbacks"), list):
        for item in slot["fallbacks"]:
            if isinstance(item, dict):
                raw_fallbacks.append(item)
    elif isinstance(slot.get("fallback"), dict):
        raw_fallbacks.append(slot["fallback"])

    configs: list[ModelConfig] = []
    seen: set[tuple[str, str | None]] = set()

    for fb in raw_fallbacks:
        provider_id = str(fb.get("providerId", ""))
        model = str(fb.get("model", ""))
        if not provider_id or not model:
            continue

        provider = next(
            (p for p in providers if isinstance(p, dict) and p.get("id") == provider_id and p.get("isEnabled")),
            None,
        )
        if not provider:
            continue

        cfg = _build_enriched_model_config(
            provider_id=provider_id,
            model=model,
            provider=provider,
            providers_dict=providers_dict,
        )
        _append_unique_model_config(configs, seen, cfg)

    return configs


def _resolve_slot_fallback(
    slot: object,
    providers: list[dict[str, object]],
    *,
    providers_dict: dict[str, object] | None = None,
    selection_supports_vision: bool = False,
    infer_video: bool = False,
) -> "ModelConfig | None":
    """Resolve the primary fallback selection within a ModelSlot to a ModelConfig."""
    if not isinstance(slot, dict):
        return None

    # Check fallbacks list first, fallback to single fallback
    fallback = None
    if isinstance(slot.get("fallbacks"), list) and slot["fallbacks"]:
        first = slot["fallbacks"][0]
        if isinstance(first, dict):
            fallback = first
    if fallback is None and isinstance(slot.get("fallback"), dict):
        fallback = slot["fallback"]

    if not isinstance(fallback, dict):
        return None

    provider_id = str(fallback.get("providerId", ""))
    model = str(fallback.get("model", ""))
    if not provider_id or not model:
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
        selection_supports_vision=selection_supports_vision,
        infer_video=infer_video,
    )
