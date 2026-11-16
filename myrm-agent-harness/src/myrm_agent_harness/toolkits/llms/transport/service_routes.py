"""Endpoint resolution for the non-chat model services (embeddings, reranking, image generation).

[INPUT]
- transport.endpoint (POS: the grammar that reduces a user's address to a root and a query)
- transport.profile (POS: PROFILES, ProviderProfile, Route, UnsupportedProviderError)

[OUTPUT]
- SERVICE_PROFILES: the providers that serve embeddings, rerank or images and no chat
- service_route: the provider, bare model id, endpoint root and credential of an embedding, rerank or image call

[POS]
Embedding, rerank and image providers are a different set from the chat providers (Jina, Voyage, Cohere,
Stability and MiniMax image serve no chat), so they get their own small table next to the chat profiles instead
of widening ``PROFILES``. A provider with a default endpoint resolves from the ``provider/model`` id; any other
id is an OpenAI-compatible endpoint and needs an ``api_base``, keeping the whole id as the model name
(``BAAI/bge-m3`` is a model, not a provider). An endpoint comes from the call, else from the provider's own
endpoint variable (``OPENAI_BASE_URL``, ``AZURE_API_BASE``, ...), else from its default; only an explicitly passed
credential is used: these calls never read provider keys from the environment.
"""

from __future__ import annotations

from typing import Final

from myrm_agent_harness.toolkits.llms.transport.endpoint import NO_QUERY, Endpoint, InvalidEndpointError, parse_endpoint
from myrm_agent_harness.toolkits.llms.transport.profile import (
    PROFILES,
    ProviderProfile,
    Route,
    UnsupportedProviderError,
    first_env,
)

SERVICE_PROFILES: Final[dict[str, ProviderProfile]] = {
    "jina_ai": ProviderProfile(id="jina_ai", base_url="https://api.jina.ai/v1", api_base_env=("JINA_AI_API_BASE",)),
    "voyage": ProviderProfile(id="voyage", base_url="https://api.voyageai.com/v1", api_base_env=("VOYAGE_API_BASE",)),
    "cohere": ProviderProfile(id="cohere", base_url="https://api.cohere.com/v2", api_base_env=("COHERE_API_BASE",)),
    "stability": ProviderProfile(id="stability", base_url="https://api.stability.ai"),
    "minimax_image": ProviderProfile(id="minimax_image", base_url="https://api.minimax.io"),
}
_OPENAI_FAMILY_BARE: Final = ("text-embedding-", "gpt-image")
_ENDPOINT_SUFFIXES: Final = ("/embeddings", "/embed", "/rerank", "/images/generations", "/images/edits")
# Ids a custom endpoint still reads as its own scheme; every other ``provider/model`` there is a gateway route.
_OWN_SCHEME_UNDER_BASE: Final = frozenset({"openai", "azure"})


def _endpoint(url: str | None) -> Endpoint | None:
    """The root and query of an address: callers may pass a root or the full operation URL."""
    if not url or not url.strip():
        return None
    try:
        return parse_endpoint(url, _ENDPOINT_SUFFIXES)
    except InvalidEndpointError as exc:
        raise UnsupportedProviderError(str(exc)) from exc


def _route(profile: ProviderProfile, model: str, endpoint: Endpoint | None, api_key: str | None) -> Route:
    """A route to ``endpoint``, else to the provider's default endpoint."""
    return Route(
        profile=profile,
        model=model,
        base_url=endpoint.root if endpoint else profile.base_url,
        api_key=api_key,
        query=endpoint.query if endpoint else NO_QUERY,
    )


def _provider_endpoint(profile: ProviderProfile) -> Endpoint | None:
    """The endpoint a call that names none reaches before the provider's default: its own variable."""
    return _endpoint(first_env(profile.api_base_env))


def service_route(model: str, *, api_key: str | None, api_base: str | None, gateway_base: bool = False) -> Route:
    """Resolve ``model`` (``provider/id``, a bare OpenAI-family id, or any id with an ``api_base``).

    ``gateway_base`` reads a custom ``api_base`` as an OpenAI-compatible gateway (LiteLLM proxy, One API, vLLM) that
    routes on the whole model id, so ``jina_ai/jina-embeddings-v3`` keeps its prefix instead of selecting the Jina API.
    """
    given = _endpoint(api_base)
    segment, separator, rest = model.partition("/")
    provider = segment.lower()
    profile = (SERVICE_PROFILES.get(provider) or PROFILES.get(provider)) if separator else None
    if gateway_base and given and provider not in _OWN_SCHEME_UNDER_BASE:
        profile = None
    if profile is not None:
        return _route(profile, rest, given or _provider_endpoint(profile), api_key)
    if given:
        return _route(ProviderProfile(id="openai_compatible"), model, given, api_key)
    if model.lower().startswith(_OPENAI_FAMILY_BARE):
        openai = PROFILES["openai"]
        return _route(openai, model, _provider_endpoint(openai), api_key)
    raise UnsupportedProviderError(
        f"Cannot resolve a provider for model '{model}': use a 'provider/model' id or set an api_base"
    )
