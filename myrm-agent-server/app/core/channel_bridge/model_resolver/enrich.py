"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- _resolve_model_max_input_tokens, _lookup_custom_model_info, _resolve_supports_vision_from_litellm, enrich_model_capabilities, enrich_model_context_window

[POS]
Model resolver: context-window and capability enrichment from custom model info / litellm metadata.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.types import ModelConfig


logger = logging.getLogger(__name__)


def _resolve_model_max_input_tokens(
    model: str,
    providers_dict: dict[str, object] | None,
) -> int | None:
    """Query the true max_input_tokens for a model.

    Priority: user customModelInfo > litellm built-in data.
    Returns None if the model is unknown (caller falls back to 128K).
    """
    if providers_dict and isinstance(providers_dict, dict):
        custom_info = providers_dict.get("customModelInfo")
        if isinstance(custom_info, dict):
            info = custom_info.get(model)
            if isinstance(info, dict):
                val = info.get("max_input_tokens")
                if isinstance(val, (int, float)) and val > 0:
                    return int(val)
            for key, info_val in custom_info.items():
                if not isinstance(info_val, dict):
                    continue
                if key.split("/", 1)[-1] == model.split("/", 1)[-1]:
                    val = info_val.get("max_input_tokens")
                    if isinstance(val, (int, float)) and val > 0:
                        return int(val)

    try:
        import litellm

        info = litellm.get_model_info(model.lower())
        if info:
            max_input = info.get("max_input_tokens")
            if isinstance(max_input, int) and max_input > 0:
                return max_input
            max_tokens = info.get("max_tokens")
            if isinstance(max_tokens, int) and max_tokens > 0:
                return max_tokens
    except Exception:
        pass

    return None


def _lookup_custom_model_info(
    model: str,
    providers_dict: dict[str, object] | None,
) -> dict[str, object] | None:
    """Return customModelInfo entry for a model (supports providerId/model keys)."""
    if not providers_dict or not isinstance(providers_dict, dict):
        return None
    custom_info = providers_dict.get("customModelInfo")
    if not isinstance(custom_info, dict):
        return None
    direct = custom_info.get(model)
    if isinstance(direct, dict):
        return direct
    bare = model.split("/", 1)[-1]
    direct = custom_info.get(bare)
    if isinstance(direct, dict):
        return direct
    for key, info_val in custom_info.items():
        if isinstance(info_val, dict) and key.split("/", 1)[-1] == bare:
            return info_val
    return None


def _resolve_supports_vision_from_litellm(model: str) -> bool | None:
    bare = model.split("/", 1)[-1].lower()
    try:
        import litellm

        info = litellm.get_model_info(bare)
        if not info:
            return None
        if info.get("supports_vision") or info.get("supports_image_input"):
            return True
        if info.get("supports_vision") is False:
            return False
    except Exception:
        return None
    return None


def enrich_model_capabilities(
    cfg: "ModelConfig",
    providers_dict: dict[str, object] | None,
    *,
    selection_supports_vision: bool | None = None,
) -> "ModelConfig":
    """Enrich supports_vision from frontend selection, customModelInfo, or litellm."""
    if selection_supports_vision is not None:
        return cfg.model_copy(update={"supports_vision": selection_supports_vision})

    custom = _lookup_custom_model_info(cfg.model, providers_dict)
    if custom is not None and "supports_vision" in custom:
        return cfg.model_copy(update={"supports_vision": bool(custom["supports_vision"])})

    litellm_vision = _resolve_supports_vision_from_litellm(cfg.model)
    if litellm_vision is not None:
        return cfg.model_copy(update={"supports_vision": litellm_vision})

    return cfg


def enrich_model_context_window(
    cfg: "ModelConfig",
    providers_dict: dict[str, object] | None,
) -> "ModelConfig":
    """Enrich a ModelConfig with the model's true max_context_tokens.

    If max_context_tokens is already set, returns the config unchanged.
    Otherwise queries customModelInfo / litellm for the model's real
    max_input_tokens and returns a new ModelConfig with it set.
    """
    if cfg.max_context_tokens is not None:
        return cfg

    max_input = _resolve_model_max_input_tokens(cfg.model, providers_dict)
    if max_input is not None:
        return cfg.model_copy(update={"max_context_tokens": max_input})

    return cfg
