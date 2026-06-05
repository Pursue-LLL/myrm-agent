"""Model resolution and custom pricing registration.

Resolves model configs from providers and registers custom model pricing
into litellm.model_cost for completion cost calculation.

All resolved models are explicitly configured and visible to the user via the
frontend GUI. No implicit/hidden fallback to arbitrary providers.

[INPUT]
- providers_dict: dict from frontend providers config
- model_override: optional LiteLLM model name

[OUTPUT]
- resolve_model_config: build ModelConfig for specific model or user default
- register_custom_model_pricing: register user-defined costs into litellm
- _fallback_model_from_providers: resolve user's default model (no hidden fallback)

[POS]
Business-layer model resolution. Uses framework-level parsers (to_litellm_model, parse_litellm_model)
for LiteLLM format conversion, combined with business-specific provider config parsing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.agent.config import ConfigIncompleteError
from myrm_agent_harness.agent.config.parsers import (
    parse_litellm_model,
    to_litellm_model,
)

if TYPE_CHECKING:
    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)

_PROVIDER_API_BASES: dict[str, str] = {
    "siliconflow": "https://api.siliconflow.cn/v1",
}


def resolve_model_config(
    providers_dict: dict[str, object] | None,
    model_override: str | None = None,
) -> "ModelConfig":
    """Build ModelConfig for a specific model or the user's default.

    If ``model_override`` is given (LiteLLM format like "openai/gpt-4o-mini"),
    looks up the corresponding provider's API key and base URL.
    Falls back to the user's default model if the override is invalid.
    """
    if model_override and providers_dict:
        cfg = _resolve_override(providers_dict, model_override)
        if cfg:
            return cfg
        logger.warning(
            "model_resolver: model override '%s' not resolvable for sandbox, falling back to default",
            model_override,
        )

    return _fallback_model_from_providers(providers_dict)


def register_custom_model_pricing(providers_dict: dict[str, object] | None) -> int:
    """Register user-defined model pricing into litellm.model_cost.

    Reads customModelInfo from providers config and registers input/output
    cost for models that have user-defined pricing. This enables
    litellm.completion_cost() to return meaningful costs for self-hosted
    models (Ollama, vLLM, LM Studio) that have no built-in price table.

    Note: Frontend stores costs as $/million-tokens (matching models.dev),
    while litellm expects $/token. This function performs the conversion.

    Returns the number of models registered.
    """
    if not providers_dict or not isinstance(providers_dict, dict):
        return 0

    custom_info = providers_dict.get("customModelInfo")
    if not isinstance(custom_info, dict) or not custom_info:
        return 0

    try:
        import litellm
    except ImportError:
        return 0

    provider_type_map = _build_provider_type_map(providers_dict)

    registered = 0
    for model_key, info in custom_info.items():
        if not isinstance(info, dict):
            continue

        input_cost_per_m = info.get("input_cost_per_million")
        output_cost_per_m = info.get("output_cost_per_million")

        if not isinstance(input_cost_per_m, (int, float)) or not isinstance(output_cost_per_m, (int, float)):
            continue
        if input_cost_per_m <= 0 and output_cost_per_m <= 0:
            continue

        parts = model_key.split("/", 1)
        if len(parts) != 2:
            continue
        provider_id, raw_model = parts[0], parts[1]

        ptype = provider_type_map.get(provider_id)
        litellm_model = _to_litellm_model(provider_id, raw_model, ptype)

        litellm.model_cost[litellm_model] = {
            "input_cost_per_token": float(input_cost_per_m) / 1_000_000,
            "output_cost_per_token": float(output_cost_per_m) / 1_000_000,
            "max_tokens": info.get("max_input_tokens") or 128_000,
            "litellm_provider": "custom",
        }
        registered += 1

    if registered:
        logger.info("Registered custom pricing for %d model(s)", registered)

    return registered


def _fallback_model_from_providers(
    providers_dict: dict[str, object] | None,
    user_id: str | None = None,
) -> "ModelConfig":
    """Build ModelConfig from the user's explicit default model config.

    Priority: defaultModelConfig.baseModel.primary > ConfigIncompleteError.

    No implicit fallback to environment variables or "first enabled provider".
    """
    from app.core.types import ModelConfig

    if not providers_dict:
        raise ConfigIncompleteError(
            user_friendly_message={
                "en": "Please configure at least one LLM provider before using the Agent.",
                "zh": "请先配置至少一个 LLM 提供商，然后再使用 Agent 功能。",
            },
            technical_details="No providers config in WebUI settings",
            resolution_steps=[
                "Go to Settings > Model Service",
                "Add and enable at least one provider (OpenAI, Anthropic, Ollama, etc.)",
                "Ensure the provider has a valid API key (or is running for local providers)",
            ],
            error_code="provider_not_configured",
        )

    providers: list[dict[str, object]] = []
    if isinstance(providers_dict, dict):
        providers_raw = providers_dict.get("providers")
        if isinstance(providers_raw, list):
            providers = providers_raw
    providers_by_id = {str(p.get("id", "")): p for p in providers if isinstance(p, dict)}

    default_model_cfg = {}
    if isinstance(providers_dict, dict):
        default_model_cfg = providers_dict.get("defaultModelConfig", {})
    if isinstance(default_model_cfg, dict):
        base_model = default_model_cfg.get("baseModel") or {}
        base_selection = base_model.get("primary") or base_model.get("selection")
        if base_selection and isinstance(base_selection, dict):
            pid = str(base_selection.get("providerId", ""))
            model = str(base_selection.get("model", ""))
            provider = providers_by_id.get(pid)
            is_enabled = provider.get("isEnabled") or provider.get("enabled") if provider else False
            if provider and is_enabled and model:
                all_keys = _extract_all_active_keys(provider)
                if all_keys:
                    ptype = str(provider.get("providerType", "")) or None
                    full_model = _to_litellm_model(pid, model, ptype)
                    api_url = str(provider.get("apiUrl") or provider.get("baseURL") or "")
                    api_url = api_url if api_url else None
                    logger.debug("model_resolver: using default model %s", full_model)
                    return ModelConfig(
                        model=full_model,
                        api_key=all_keys[0],
                        base_url=api_url,
                        api_keys=all_keys if len(all_keys) > 1 else None,
                    )

    raise ConfigIncompleteError(
        user_friendly_message={
            "en": "No default model configured. Please select a default model in Settings.",
            "zh": "未配置默认模型，请在设置中选择一个默认模型。",
        },
        technical_details="No defaultModelConfig found in WebUI providers settings",
        resolution_steps=[
            "Go to Settings > Model Service",
            "Select a default model from an enabled provider",
            "Ensure the provider has a valid API key",
        ],
        error_code="default_model_not_configured",
    )


def _resolve_override(providers_dict: dict[str, object], model_name: str) -> "ModelConfig | None":
    """Try to build a ModelConfig from providers for the given LiteLLM model name."""
    from app.core.types import ModelConfig

    provider_id, raw_model = _parse_litellm_model(model_name)

    providers: list[dict[str, object]] = providers_dict.get("providers", [])  # type: ignore[assignment]

    openai_compat_ids = {
        "openai",
        "siliconflow",
        "openai_compatible",
        "openai_like",
        "openai-compatible",
        "openai-like",
    }

    for p in providers:
        is_enabled = p.get("isEnabled") or p.get("enabled")
        if not is_enabled:
            continue
        pid = str(p.get("id", ""))
        ptype = str(p.get("providerType", ""))

        is_exact = pid == provider_id
        is_compat = provider_id in openai_compat_ids and (pid in openai_compat_ids or ptype == provider_id)
        if not is_exact and not is_compat:
            continue

        enabled_models: list[str] = p.get("enabledModels", [])  # type: ignore[assignment]
        if enabled_models and raw_model not in enabled_models:
            continue

        all_keys = _extract_all_active_keys(p)
        if not all_keys:
            continue
        api_url = str(p.get("apiUrl") or p.get("baseURL") or "")
        api_url = api_url if api_url else None
        resolved_model = _to_litellm_model(pid, raw_model, ptype or None)
        return ModelConfig(
            model=resolved_model,
            api_key=all_keys[0],
            base_url=api_url,
            api_keys=all_keys if len(all_keys) > 1 else None,
        )

    return None


def _parse_litellm_model(model_name: str) -> tuple[str, str]:
    """Parse a LiteLLM model name (wrapper for framework-level parser)."""
    return cast(tuple[str, str], parse_litellm_model(model_name))


def _extract_active_key(provider: dict[str, object]) -> str | None:
    """Extract the first active API key from a provider config dict."""
    keys = _extract_all_active_keys(provider)
    return keys[0] if keys else None


def _extract_all_active_keys(provider: dict[str, object]) -> list[str]:
    """Extract all active API keys from a provider config dict.

    Returns a list of active keys (may be empty). Used by credential pool
    for key rotation on rate-limit errors.
    """
    raw: object = provider.get("apiKeys")
    if not isinstance(raw, list):
        alt = provider.get("api_keys")
        raw = alt if isinstance(alt, list) else None
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        active = entry.get("isActive")
        if active is None:
            active = entry.get("is_active")
        key_raw = entry.get("key")
        if active and key_raw is not None:
            out.append(str(key_raw))
    return out


def _to_litellm_model(provider: str, model: str, provider_type: str | None = None) -> str:
    """Convert provider + model to LiteLLM format (wrapper for framework-level converter)."""
    return str(to_litellm_model(provider, model, provider_type))


def _normalize_model_name(model: str) -> str:
    """Normalize model name to LiteLLM-compatible format.

    Converts legacy/alternative provider prefixes to standard LiteLLM format:
    - openai-compatible/ -> openai/
    - openai_compatible/ -> openai/
    - gemini-compatible/ -> gemini/
    - anthropic-compatible/ -> anthropic/

    Args:
        model: Raw model name from config (e.g., "openai-compatible/deepseek-v4-flash")

    Returns:
        Normalized model name (e.g., "openai/deepseek-v4-flash")
    """
    if "/" not in model:
        return model

    prefix, model_name = model.split("/", 1)
    prefix_lower = prefix.lower().replace("-", "_")

    if prefix_lower in ("openai_compatible", "openai_like", "siliconflow"):
        return f"openai/{model_name}"
    elif prefix_lower in ("gemini_compatible", "gemini_like"):
        return f"gemini/{model_name}"
    elif prefix_lower in ("anthropic_compatible", "anthropic_like"):
        return f"anthropic/{model_name}"
    elif prefix_lower == "minimax":
        return f"minimax/{model_name}"
    elif prefix_lower == "xiaomi":
        return f"xiaomi_mimo/{model_name}"
    elif prefix_lower == "xiaomi_mimo":
        return model

    return model


def _build_provider_type_map(
    providers_dict: dict[str, object],
) -> dict[str, str | None]:
    """Build {provider_id: providerType} map from providers list."""
    providers = providers_dict.get("providers")
    if not isinstance(providers, list):
        return {}
    result: dict[str, str | None] = {}
    for p in providers:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", ""))
        ptype = str(p.get("providerType", "")) or None
        if pid:
            result[pid] = ptype
    return result


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


__all__ = [
    "resolve_model_config",
    "register_custom_model_pricing",
    "enrich_model_context_window",
    "enrich_model_capabilities",
    "_fallback_model_from_providers",
    "_extract_active_key",
    "_extract_all_active_keys",
    "_to_litellm_model",
]
