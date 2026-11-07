"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- _resolve_model_max_input_tokens, _lookup_custom_model_info, _resolve_supports_vision_from_catalog, enrich_model_capabilities, enrich_model_context_window

[POS]
Model resolver: context-window and capability enrichment from custom model info / the model catalog.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.llms.catalog import model_facts

if TYPE_CHECKING:
    from app.core.types import ModelConfig


logger = logging.getLogger(__name__)


def _resolve_model_max_input_tokens(
    model: str,
    providers_dict: dict[str, object] | None,
) -> int | None:
    """Query the true max_input_tokens for a model.

    Priority: user customModelInfo > the model catalog.
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

    window = (model_facts(model) or {}).get("max_input_tokens")
    return window if isinstance(window, int) and window > 0 else None


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


def _resolve_supports_vision_from_catalog(model: str) -> bool | None:
    vision = (model_facts(model) or {}).get("supports_vision")
    return vision if isinstance(vision, bool) else None


def enrich_model_capabilities(
    cfg: "ModelConfig",
    providers_dict: dict[str, object] | None,
    *,
    selection_supports_vision: bool | None = None,
) -> "ModelConfig":
    """Enrich supports_vision from frontend selection, customModelInfo, or the model catalog."""
    if selection_supports_vision is not None:
        return cfg.model_copy(update={"supports_vision": selection_supports_vision})

    custom = _lookup_custom_model_info(cfg.model, providers_dict)
    if custom is not None and "supports_vision" in custom:
        return cfg.model_copy(update={"supports_vision": bool(custom["supports_vision"])})

    catalog_vision = _resolve_supports_vision_from_catalog(cfg.model)
    if catalog_vision is not None:
        return cfg.model_copy(update={"supports_vision": catalog_vision})

    return cfg


def enrich_model_context_window(
    cfg: "ModelConfig",
    providers_dict: dict[str, object] | None,
) -> "ModelConfig":
    """Enrich a ModelConfig with the model's true max_context_tokens.

    If max_context_tokens is already set, returns the config unchanged.
    Otherwise queries customModelInfo / the model catalog for the model's real
    max_input_tokens and returns a new ModelConfig with it set.
    """
    if cfg.max_context_tokens is not None:
        return cfg

    max_input = _resolve_model_max_input_tokens(cfg.model, providers_dict)
    if max_input is not None:
        return cfg.model_copy(update={"max_context_tokens": max_input})

    return cfg
