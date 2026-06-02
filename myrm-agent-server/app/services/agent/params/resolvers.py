from __future__ import annotations

import logging

from app.core.types import ModelConfig

from .models import ModelSelection
from .providers import _find_provider_api_key

logger = logging.getLogger(__name__)


def _resolve_provider_base_url(
    _provider_id: str,
    selection_base_url: str | None,
) -> str | None:
    """Resolve base URL from explicit selection only."""

    if selection_base_url:
        return selection_base_url

    return None


async def _resolve_model_config(
    selection: ModelSelection,
    providers_dict: dict[str, object] | None,
) -> ModelConfig:
    """Resolve a ModelSelection into a full ModelConfig with API key from WebUI providers."""
    from app.core.channel_bridge.model_resolver import (
        _extract_all_active_keys,
        _to_litellm_model,
    )

    if selection.provider_id == "default" or selection.provider_id == "auto":
        from app.core.channel_bridge.model_resolver import _fallback_model_from_providers

        return _fallback_model_from_providers(providers_dict)

    providers = (
        providers_dict.get("providers") if isinstance(providers_dict, dict) else []
    )
    logger.info(f"Resolving model config for {selection.provider_id}")
    logger.info(f"Providers dict: {providers_dict}")

    if not isinstance(providers, list) and isinstance(providers, dict):
        # Handle case where providers is a dict (like our injected minimax config)
        if selection.provider_id in providers:
            provider = providers[selection.provider_id]
            # Ensure it has the structure expected later
            if isinstance(provider, dict) and (
                provider.get("isEnabled") or provider.get("enabled")
            ):
                provider["id"] = selection.provider_id
                providers = [provider]
            else:
                providers = []
        else:
            providers = []

    if not isinstance(providers, list):
        providers = []

    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict)
            and p.get("id") == selection.provider_id
            and p.get("isEnabled")
        ),
        None,
    )

    all_keys: list[str] = []
    if provider:
        all_keys = _extract_all_active_keys(provider)
        provider_type = str(provider.get("providerType", "")) or None
        api_url = selection.base_url or str(provider.get("apiUrl", "")) or None
    else:
        fallback_key = _find_provider_api_key(providers_dict, selection.provider_id)

        if fallback_key:
            all_keys = [fallback_key]
            provider_type = None
            api_url = _resolve_provider_base_url(selection.provider_id, selection.base_url)

    if not all_keys:
        raise ValueError(f"No active API key for provider '{selection.provider_id}'")

    full_model = _to_litellm_model(
        selection.provider_id, selection.model, provider_type
    )

    return ModelConfig(
        model=full_model,
        api_key=all_keys[0],
        base_url=api_url,
        model_kwargs=selection.model_kwargs,
        api_keys=all_keys if len(all_keys) > 1 else None,
        credential_pool_strategy=selection.credential_pool_strategy,
    )
