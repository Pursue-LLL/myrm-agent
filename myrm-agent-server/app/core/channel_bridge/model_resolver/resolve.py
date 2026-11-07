"""[INPUT]
- .common (POS: headers / keys / provider/model naming)

[OUTPUT]
- resolve_model_config, validate_model_override, _fallback_model_from_providers, _resolve_override

[POS]
Model resolver: model config resolution: user default fallback, override resolution and validation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.api import ConfigIncompleteError

from app.core.wire.enrich import enrich_model_config

if TYPE_CHECKING:
    from app.core.types import ModelConfig

from .common import (
    _build_transport_headers,
    _extract_all_active_keys,
    _parse_route_model_id,
    _to_route_model_id,
)

logger = logging.getLogger(__name__)


def resolve_model_config(
    providers_dict: dict[str, object] | None,
    model_override: str | None = None,
) -> "ModelConfig":
    """Build ModelConfig for a specific model or the user's default.

    If ``model_override`` is given (routed form like "openai/gpt-4o-mini"),
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


def validate_model_override(
    providers_dict: dict[str, object] | None,
    model_override: str | None,
) -> str:
    """Validate a per-task model override is resolvable.

    Returns an empty string when the override is valid (or empty); otherwise
    a human-readable reason. Used by API layers to reject invalid overrides
    with a 400 before persistence, preventing silent fallback at runtime.
    """
    if not model_override:
        return ""
    if not providers_dict:
        return "No LLM providers are configured"
    if _resolve_override(providers_dict, model_override) is None:
        return (
            f"Model '{model_override}' is not available in any enabled "
            "provider; check the provider name and that the model is enabled"
        )
    return ""


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
        if not base_selection and default_model_cfg.get("providerId") and default_model_cfg.get("model"):
            base_selection = default_model_cfg
        if base_selection and isinstance(base_selection, dict):
            pid = str(base_selection.get("providerId", ""))
            model = str(base_selection.get("model") or base_selection.get("modelId") or "")
            provider = providers_by_id.get(pid)
            is_enabled = provider.get("isEnabled") or provider.get("enabled") if provider else False
            if provider and is_enabled and model:
                all_keys = _extract_all_active_keys(provider)
                if all_keys:
                    ptype = str(provider.get("providerType", "")) or None
                    full_model = _to_route_model_id(pid, model, ptype)
                    oauth_base = provider.get("_oauthBaseUrl")
                    api_url = str(oauth_base) if oauth_base else str(provider.get("apiUrl") or provider.get("baseURL") or "")
                    api_url = api_url if api_url else None
                    egress_proxy_raw = provider.get("egressProxy") or provider.get("egress_proxy")
                    egress_proxy = str(egress_proxy_raw).strip() or None if egress_proxy_raw else None
                    pool_strategy = str(provider.get("credentialPoolStrategy", "")) or None
                    model_kwargs = _build_transport_headers(all_keys[0], pid, api_url)
                    # Warn if default base model is a preview/beta slug
                    model_lower = model.lower()
                    if any(frag in model_lower for frag in ("preview", "-preview-", "beta", "experimental")):
                        logger.warning(
                            "Default model '%s' is a preview/experimental model. "
                            "Consider using a stable release for default position to prevent silent behavior drift.",
                            model,
                        )
                    logger.debug("model_resolver: using default model %s", full_model)
                    return enrich_model_config(
                        ModelConfig(
                            model=full_model,
                            api_key=all_keys[0],
                            base_url=api_url,
                            api_keys=all_keys if len(all_keys) > 1 else None,
                            credential_pool_strategy=pool_strategy if len(all_keys) > 1 else None,
                            egress_proxy=egress_proxy,
                            model_kwargs=model_kwargs,
                        ),
                        provider_id=pid,
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
    """Try to build a ModelConfig from providers for the given routed model name."""
    from app.core.types import ModelConfig

    provider_id, raw_model = _parse_route_model_id(model_name)

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
        if enabled_models:
            matched = raw_model in enabled_models or (
                pid == "vercel_ai_gateway"
                and raw_model.removeprefix("vercel_ai_gateway/") in {m.removeprefix("vercel_ai_gateway/") for m in enabled_models}
            )
            if not matched:
                continue

        all_keys = _extract_all_active_keys(p)
        if not all_keys:
            continue
        # OAuth-injected base_url takes precedence (e.g. the xAI SuperGrok endpoint)
        oauth_base = p.get("_oauthBaseUrl")
        api_url = str(oauth_base) if oauth_base else str(p.get("apiUrl") or p.get("baseURL") or "")
        api_url = api_url if api_url else None
        egress_proxy_raw = p.get("egressProxy") or p.get("egress_proxy")
        egress_proxy = str(egress_proxy_raw).strip() or None if egress_proxy_raw else None
        pool_strategy = str(p.get("credentialPoolStrategy", "")) or None
        resolved_model = _to_route_model_id(pid, raw_model, ptype or None)
        model_kwargs = _build_transport_headers(all_keys[0], pid, api_url)
        return enrich_model_config(
            ModelConfig(
                model=resolved_model,
                api_key=all_keys[0],
                base_url=api_url,
                api_keys=all_keys if len(all_keys) > 1 else None,
                credential_pool_strategy=pool_strategy if len(all_keys) > 1 else None,
                egress_proxy=egress_proxy,
                model_kwargs=model_kwargs,
            ),
            provider_id=pid,
        )

    return None
