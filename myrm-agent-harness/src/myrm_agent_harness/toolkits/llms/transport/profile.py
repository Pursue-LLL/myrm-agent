"""Provider profiles and route resolution for the model transport.

[INPUT]
- (none) Pure data and string transforms.

[OUTPUT]
- ProviderProfile: what one provider needs on the wire (protocol, default endpoint, credential variables, body quirks)
- PROFILES: the built-in providers keyed by the first segment of a ``segment/model`` id
- Route / resolve_route: the profile, bare model id, endpoint and credential one call resolves to
- UnsupportedProviderError: the model names a provider this transport cannot reach

[POS]
Data-driven provider knowledge. Adding an OpenAI-compatible provider is one entry here; a provider with its
own protocol additionally gets a wire module. The ``segment/model`` id format is the persisted one, so settings
and saved model selections need no migration. Provider resolution is an explicit table, never a hidden rule.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal
from urllib.parse import urlsplit, urlunsplit

Wire = Literal["openai_chat", "azure_openai", "anthropic", "gemini", "ollama"]
TextFlattening = Literal["never", "text_only", "always"]
# Whether the provider's chat endpoint accepts ``cache_control`` marks on messages and tools: never (they are
# stripped), always, or only when the call goes to a custom endpoint (a gateway that may front a caching model).
CacheControl = Literal["never", "always", "custom_base"]

_EMPTY: Final[Mapping[str, object]] = MappingProxyType({})
_EMPTY_HEADERS: Final[Mapping[str, str]] = MappingProxyType({})

# OpenAI reasoning families reject `max_tokens` and any temperature other than 1.
_OPENAI_REASONING_MODEL: Final = re.compile(r"^(?:o[1-9]\d*(?:[-.]|$)|gpt-5(?!.*chat)|codex)", re.IGNORECASE)


class UnsupportedProviderError(ValueError):
    """The model id names a provider that has no transport."""


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Wire-level facts of one provider."""

    id: str
    wire: Wire = "openai_chat"
    base_url: str | None = None
    api_key_env: tuple[str, ...] = ()
    # Providers whose API rejects ``content`` arrays of text parts get a plain string instead.
    flatten_text: TextFlattening = "never"
    # Body fields the provider needs on every chat call (merged under the caller's own).
    extra_body: Mapping[str, object] = field(default=_EMPTY)
    # Models matching this pattern use `max_completion_tokens` and accept only temperature 1.
    reasoning_model: re.Pattern[str] | None = None
    # Request headers the provider expects on every call (under the caller's own).
    headers: Mapping[str, str] = field(default=_EMPTY_HEADERS)
    cache_control: CacheControl = "never"
    # Whether the provider serves the OpenAI Responses endpoint next to chat completions.
    responses: bool = False


def _profile(
    id: str,
    base_url: str | None,
    *env: str,
    wire: Wire = "openai_chat",
    flatten_text: TextFlattening = "never",
    extra_body: Mapping[str, object] = _EMPTY,
    reasoning_model: re.Pattern[str] | None = None,
    headers: Mapping[str, str] = _EMPTY_HEADERS,
    cache_control: CacheControl = "never",
    responses: bool = False,
) -> ProviderProfile:
    return ProviderProfile(
        id=id,
        wire=wire,
        base_url=base_url,
        api_key_env=env,
        flatten_text=flatten_text,
        extra_body=extra_body,
        reasoning_model=reasoning_model,
        headers=headers,
        cache_control=cache_control,
        responses=responses,
    )


PROFILES: Final[dict[str, ProviderProfile]] = {
    p.id: p
    for p in (
        _profile(
            "openai",
            "https://api.openai.com/v1",
            "OPENAI_API_KEY",
            reasoning_model=_OPENAI_REASONING_MODEL,
            cache_control="custom_base",
            responses=True,
        ),
        _profile(
            "azure",
            None,
            "AZURE_API_KEY",
            "AZURE_OPENAI_API_KEY",
            wire="azure_openai",
            reasoning_model=_OPENAI_REASONING_MODEL,
            cache_control="always",
            responses=True,
        ),
        _profile("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", wire="anthropic"),
        _profile(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            wire="gemini",
        ),
        _profile("ollama", "http://localhost:11434", "OLLAMA_API_KEY", wire="ollama"),
        _profile("deepseek", "https://api.deepseek.com", "DEEPSEEK_API_KEY", flatten_text="always"),
        _profile(
            "openrouter",
            "https://openrouter.ai/api/v1",
            "OPENROUTER_API_KEY",
            extra_body=MappingProxyType({"usage": {"include": True}}),
            cache_control="always",
            responses=True,
        ),
        _profile("zai", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", cache_control="always"),
        _profile("xai", "https://api.x.ai/v1", "XAI_API_KEY", responses=True),
        _profile("moonshot", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY", flatten_text="text_only"),
        _profile("lm_studio", "http://localhost:1234/v1", "LM_STUDIO_API_KEY"),
        _profile("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", flatten_text="text_only"),
        _profile("together_ai", "https://api.together.xyz/v1", "TOGETHERAI_API_KEY", "TOGETHER_API_KEY"),
        _profile(
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3",
            "VOLCENGINE_API_KEY",
            "ARK_API_KEY",
            responses=True,
        ),
        _profile(
            "fireworks_ai",
            "https://api.fireworks.ai/inference/v1",
            "FIREWORKS_API_KEY",
            "FIREWORKS_AI_API_KEY",
        ),
        _profile("minimax", "https://api.minimax.io/v1", "MINIMAX_API_KEY", cache_control="always"),
        _profile("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
        _profile(
            "dashscope",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "DASHSCOPE_API_KEY",
            cache_control="always",
        ),
        _profile("perplexity", "https://api.perplexity.ai", "PERPLEXITYAI_API_KEY", "PERPLEXITY_API_KEY"),
        _profile("cohere_chat", "https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
        _profile("cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
        _profile("xiaomi_mimo", "https://api.xiaomimimo.com/v1", "XIAOMI_MIMO_API_KEY"),
        _profile(
            "yunshu",
            "http://yunshu.koolearn.com/yunshu/openai/v1",
            "YUNSHU_API_KEY",
            extra_body=MappingProxyType({"temperature": 0.2}),
            headers=MappingProxyType({"User-Agent": "YunShu-AI-SDK/2.1"}),
        ),
    )
}

_UNSUPPORTED: Final = frozenset({"replicate", "bedrock"})

# A model id without a provider segment: the family prefix names the first-party provider.
_BARE_MODEL_PROVIDER: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"^(?:gpt-|o[1-9]|chatgpt-|codex|text-embedding-|dall-e|gpt-image)", re.IGNORECASE), "openai"),
    (re.compile(r"^claude", re.IGNORECASE), "anthropic"),
    (re.compile(r"^gemini", re.IGNORECASE), "gemini"),
)

_CHAT_SUFFIXES: Final = ("/chat/completions", "/responses")


@dataclass(frozen=True, slots=True)
class Route:
    """Everything one model call resolves to before it is built."""

    profile: ProviderProfile
    model: str
    base_url: str | None
    api_key: str | None


def _bare_provider(model: str) -> str | None:
    for pattern, provider in _BARE_MODEL_PROVIDER:
        if pattern.match(model):
            return provider
    return None


def _split_model(model: str, custom_provider: str | None) -> tuple[str | None, str]:
    """(provider segment, bare model id) of ``model``; the segment is None when the id names none."""
    if custom_provider:
        prefix = f"{custom_provider}/"
        return custom_provider, model[len(prefix) :] if model.lower().startswith(prefix) else model
    head, sep, rest = model.partition("/")
    segment = head.lower()
    if sep and (segment in PROFILES or segment in _UNSUPPORTED):
        return segment, rest
    return None, model


def normalize_base_url(profile: ProviderProfile, base_url: str | None) -> str | None:
    """The endpoint root a wire appends its own path to; callers may pass a root or a full endpoint."""
    if not base_url:
        return None
    url = base_url.strip().rstrip("/")
    if profile.wire in {"openai_chat", "azure_openai"}:
        for suffix in _CHAT_SUFFIXES:
            if url.endswith(suffix):
                return url[: -len(suffix)]
    elif profile.wire == "anthropic":
        for suffix in ("/v1/messages", "/messages", "/v1"):
            if url.endswith(suffix):
                return url[: -len(suffix)]
    elif profile.wire == "ollama":
        for suffix in ("/v1/chat/completions", "/api/chat", "/api/generate", "/api", "/v1"):
            if url.endswith(suffix):
                return url[: -len(suffix)]
    elif profile.wire == "gemini":
        parts = urlsplit(url)
        if not parts.path:  # a bare Google host has no API version; the default endpoint carries v1beta
            return urlunsplit((parts.scheme, parts.netloc, "/v1beta", "", ""))
    return url


_OPENAI_BODY_WIRES: Final = frozenset({"openai_chat", "azure_openai"})


def speaks_openai_body(model: str, *, custom_llm_provider: str | None = None, api_base: str | None = None) -> bool:
    """Whether the provider takes an OpenAI-shaped request body (so extra body fields may ride along as-is).

    Providers with their own protocol build the body from typed parameters and reject unknown top-level fields.
    A model that resolves to no provider is treated as OpenAI-compatible, the shape unknown endpoints use.
    """
    try:
        route = resolve_route(model, custom_llm_provider=custom_llm_provider, api_base=api_base)
    except UnsupportedProviderError:
        return True
    return route.profile.wire in _OPENAI_BODY_WIRES


def _env_key(profile: ProviderProfile) -> str | None:
    for name in profile.api_key_env:
        value = os.environ.get(name)
        if value:
            return value
    return None


def resolve_route(
    model: str,
    *,
    custom_llm_provider: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> Route:
    """Resolve ``model`` (``segment/id`` or a bare family id) to its profile, endpoint and credential.

    A model whose segment is unknown is reached as an OpenAI-compatible endpoint when an ``api_base`` is
    given (self-hosted gateways, new providers); without one there is nothing to call and the id is rejected.
    """
    custom = (custom_llm_provider or "").strip().lower() or None
    segment, bare = _split_model(model, custom)
    segment = segment or _bare_provider(bare)

    if segment in _UNSUPPORTED:
        raise UnsupportedProviderError(f"Provider '{segment}' is not supported by the model transport")
    profile = PROFILES.get(segment) if segment else None
    if profile is None:
        if not api_base:
            raise UnsupportedProviderError(
                f"Cannot resolve a provider for model '{model}': use a 'provider/model' id from "
                f"{sorted(PROFILES)} or set an api_base for an OpenAI-compatible endpoint"
            )
        profile = ProviderProfile(id=segment or "openai_compatible", cache_control="always", responses=True)
        bare = model if segment is None else bare

    return Route(
        profile=profile,
        model=bare,
        base_url=normalize_base_url(profile, api_base) or profile.base_url,
        api_key=api_key or _env_key(profile),
    )
