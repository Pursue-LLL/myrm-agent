"""Endpoint resolution for the non-chat model services (embeddings, reranking, image generation).

[INPUT]
- transport.profile (POS: PROFILES, ProviderProfile, Route, UnsupportedProviderError)

[OUTPUT]
- service_route: the provider, bare model id, endpoint root and credential of an embedding, rerank or image call

[POS]
Embedding, rerank and image providers are a different set from the chat providers (Jina, Voyage, Cohere,
Stability and MiniMax image serve no chat), so they get their own small table next to the chat profiles instead
of widening ``PROFILES``. A provider with a default endpoint resolves from the ``provider/model`` id; any other
id is an OpenAI-compatible endpoint and needs an ``api_base``, keeping the whole id as the model name
(``BAAI/bge-m3`` is a model, not a provider). Only an explicitly passed credential is used: these calls never
read provider keys from the environment.
"""

from __future__ import annotations

from typing import Final

from myrm_agent_harness.toolkits.llms.transport.profile import (
    PROFILES,
    ProviderProfile,
    Route,
    UnsupportedProviderError,
)

_SERVICE_PROFILES: Final[dict[str, ProviderProfile]] = {
    "jina_ai": ProviderProfile(id="jina_ai", base_url="https://api.jina.ai/v1"),
    "voyage": ProviderProfile(id="voyage", base_url="https://api.voyageai.com/v1"),
    "cohere": ProviderProfile(id="cohere", base_url="https://api.cohere.com/v2"),
    "stability": ProviderProfile(id="stability", base_url="https://api.stability.ai"),
    "minimax_image": ProviderProfile(id="minimax_image", base_url="https://api.minimax.io"),
}
_OPENAI_FAMILY_BARE: Final = ("text-embedding-", "dall-e", "gpt-image")
_ENDPOINT_SUFFIXES: Final = ("/embeddings", "/embed", "/rerank", "/images/generations", "/images/edits")


def _root(url: str | None) -> str | None:
    """The endpoint root: callers may pass a root or the full operation URL."""
    if not url:
        return None
    root = url.strip().rstrip("/")
    for suffix in _ENDPOINT_SUFFIXES:
        if root.endswith(suffix):
            return root[: -len(suffix)]
    return root


def service_route(model: str, *, api_key: str | None, api_base: str | None) -> Route:
    """Resolve ``model`` (``provider/id``, a bare OpenAI-family id, or any id with an ``api_base``)."""
    base = _root(api_base)
    segment, separator, rest = model.partition("/")
    provider = segment.lower()
    profile = (_SERVICE_PROFILES.get(provider) or PROFILES.get(provider)) if separator else None
    if profile is not None:
        return Route(profile=profile, model=rest, base_url=base or profile.base_url, api_key=api_key)
    if base:
        return Route(profile=ProviderProfile(id="openai_compatible"), model=model, base_url=base, api_key=api_key)
    if model.lower().startswith(_OPENAI_FAMILY_BARE):
        openai = PROFILES["openai"]
        return Route(profile=openai, model=model, base_url=openai.base_url, api_key=api_key)
    raise UnsupportedProviderError(
        f"Cannot resolve a provider for model '{model}': use a 'provider/model' id or set an api_base"
    )
