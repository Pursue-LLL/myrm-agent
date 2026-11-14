"""OpenAI model family reasoning_effort parameter remap and normalization.

[INPUT]
- model identifier, base_url, llm_kwargs dictionary
- reasoning_route::resolve_reasoning_route (POS: provider-aware identity of a model call for reasoning-parameter rules)

[OUTPUT]
- is_openai_model(): whether the call reaches an OpenAI model (first-party endpoint, Azure, or an OpenAI model id
  behind a gateway); models other providers serve through the ``openai/`` route segment are not OpenAI models
- apply_openai_reasoning_effort(): remaps unsupported reasoning intensity values
  (e.g., 'minimal' -> 'low', 'xhigh'/'max' -> 'high') for OpenAI reasoning models
  (GPT-5.6, o1, o3, o4), and cleanly strips reasoning_effort from non-reasoning models
  (e.g., gpt-4o, gpt-4o-mini) to prevent API HTTP 400 Bad Request rejections.

[POS]
OpenAI reasoning models (such as o1, o3-mini, and GPT-5.6) natively accept only standard
``reasoning_effort`` values: ('low', 'medium', 'high'). Passing unsupported levels
such as 'minimal' (used by some frontends and agents for ultra-fast light thinking)
or 'max'/'xhigh' causes OpenAI's API to fail with HTTP 400 Bad Request.
Furthermore, non-reasoning models (such as gpt-4o and gpt-4o-mini) reject the
``reasoning_effort`` parameter entirely; if inadvertently injected into ``extra_body``,
strict gateways reject the request with HTTP 400.
This module remaps non-standard reasoning levels to OpenAI's valid enum and strips
the parameter for non-reasoning models, guaranteeing semantic intent preservation and zero 400s.
Models of other providers that merely ride the OpenAI wire (SiliconFlow, OpenCode Go, NVIDIA, custom
endpoints) keep the caller's reasoning_effort untouched: their gateway decides what it accepts.
"""

from __future__ import annotations

import logging
from typing import Any

from myrm_agent_harness.toolkits.llms.core.reasoning_route import resolve_reasoning_route

logger = logging.getLogger(__name__)

_OPENAI_HOSTS: tuple[str, ...] = ("api.openai.com",)
_OPENAI_MODEL_ID_PREFIXES: tuple[str, ...] = ("gpt-", "o1", "o3", "o4", "chatgpt-")

_OPENAI_REASONING_SUBSTRINGS: tuple[str, ...] = (
    "o1",
    "o3",
    "o4",
    "gpt-5",
    "gpt-5.6",
    "codex-reasoning",
)

_LOW_VALUES: frozenset[str] = frozenset({"low", "minimal", "min"})
_MEDIUM_VALUES: frozenset[str] = frozenset({"medium", "standard", "normal", "balanced"})
_HIGH_VALUES: frozenset[str] = frozenset({"high", "max", "xhigh", "ultra"})
_OFF_VALUES: frozenset[str] = frozenset({"off", "none", "disabled", "false", "0"})


def is_openai_model(
    model: str,
    base_url: str | None = None,
    custom_llm_provider: str | None = None,
) -> bool:
    """Return True when the call reaches an OpenAI model.

    The ``openai/`` segment only names the wire a call speaks. A model counts as OpenAI's when the endpoint is
    OpenAI's own, when the provider is Azure (which serves OpenAI models under deployment names), or when the model
    id itself is an OpenAI one behind a gateway. OpenRouter, DeepSeek and every model another provider serves through
    the ``openai/`` segment are not.
    """
    if not model:
        return False
    route = resolve_reasoning_route(model, base_url, custom_llm_provider)
    if route is None:
        return False
    if route.provider == "azure":
        return True
    at_openai_host = any(host in (base_url or "").lower() for host in _OPENAI_HOSTS)
    if route.provider == "openai":
        bare_id = route.model.rsplit("/", 1)[-1]
        return route.first_party or at_openai_host or bare_id.startswith(_OPENAI_MODEL_ID_PREFIXES)
    return route.provider == "openai_compatible" and at_openai_host


def is_openai_reasoning_model(model: str) -> bool:
    """Check if the model is an OpenAI reasoning model that supports reasoning_effort."""
    lower = model.lower()
    clean = lower.split("/")[-1]
    for prefix in ("o1", "o3", "o4", "gpt-5"):
        if clean.startswith(prefix) or f"-{prefix}" in clean:
            return True
    return any(sub in clean for sub in _OPENAI_REASONING_SUBSTRINGS)


def apply_openai_reasoning_effort(model: str, llm_kwargs: dict[str, Any]) -> None:
    """Remap or strip reasoning_effort parameter for OpenAI family models in place.

    1. For OpenAI reasoning models (o1, o3, o4, gpt-5):
       - 'minimal' / 'min' -> 'low'
       - 'max' / 'xhigh' / 'ultra' -> 'high'
       - 'standard' / 'normal' / 'balanced' -> 'medium'
       - 'off' / 'none' / '0' -> stripped (OpenAI rejects 'off' on reasoning models)
    2. For OpenAI non-reasoning models (gpt-4o, gpt-4o-mini, gpt-3.5):
       - Strips reasoning_effort from both top-level kwargs and extra_body to avoid HTTP 400.
    """
    base_url = llm_kwargs.get("api_base") or llm_kwargs.get("base_url")
    if not is_openai_model(model, base_url, llm_kwargs.get("custom_llm_provider")):
        return

    extra_body = llm_kwargs.setdefault("extra_body", {})
    raw_effort = llm_kwargs.get("reasoning_effort")
    if raw_effort is None and isinstance(extra_body, dict):
        raw_effort = extra_body.get("reasoning_effort")

    if raw_effort is None:
        return

    # Case 1: Non-reasoning model rejects reasoning_effort parameter entirely
    if not is_openai_reasoning_model(model):
        llm_kwargs.pop("reasoning_effort", None)
        if isinstance(extra_body, dict):
            extra_body.pop("reasoning_effort", None)
        logger.debug("Stripped reasoning_effort for non-reasoning OpenAI model: %s", model)
        return

    # Case 2: Reasoning model (o1, o3, gpt-5) -> Remap to valid enum ('low', 'medium', 'high')
    norm_val = str(raw_effort).strip().lower()

    if norm_val in _OFF_VALUES:
        llm_kwargs.pop("reasoning_effort", None)
        if isinstance(extra_body, dict):
            extra_body.pop("reasoning_effort", None)
        logger.debug(
            "Stripped unsupported 'off' reasoning_effort for OpenAI reasoning model: %s",
            model,
        )
        return

    if norm_val in _LOW_VALUES:
        mapped_effort = "low"
    elif norm_val in _MEDIUM_VALUES:
        mapped_effort = "medium"
    elif norm_val in _HIGH_VALUES:
        mapped_effort = "high"
    else:
        # Fallback to provider default if value is unrecognized
        mapped_effort = "medium"

    llm_kwargs["reasoning_effort"] = mapped_effort
    if isinstance(extra_body, dict):
        extra_body["reasoning_effort"] = mapped_effort

    if norm_val != mapped_effort:
        logger.info(
            "Remapped reasoning_effort '%s' -> '%s' for OpenAI model %s",
            raw_effort,
            mapped_effort,
            model,
        )
