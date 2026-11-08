"""Route model id parsing and conversion utilities.

Provides generic string manipulation functions for working with ``provider/model`` route ids.
No dependencies on business-layer configuration structures.

[INPUT]
- provider_routing::route_prefix_for_effective (POS: provider route prefix single source of truth)

[OUTPUT]
- to_route_model_id: convert provider+model to a route model id
- parse_route_model_id: parse a route model id to (provider, model)

[POS]
Framework-level utility for route model ids. Business layer can use
these functions to build route model ids from their own config structures.
"""

from __future__ import annotations

from myrm_agent_harness.agent.config.provider_routing import route_prefix_for_effective


def to_route_model_id(provider: str, model: str, provider_type: str | None = None) -> str:
    """Convert provider + model to a route model id.

    For built-in OpenAI provider (provider=="openai", no provider_type override),
    returns the bare model name (e.g. "gpt-4o").

    For custom providers with provider_type (e.g. a user-created "qwencoding" with
    provider_type="openai"), always adds the type prefix so the transport knows which wire
    to use (e.g. "openai/MiniMax-M2.5").

    Args:
        provider: Provider identifier (e.g. "openai", "anthropic")
        model: Model name (e.g. "gpt-4o", "claude-3-sonnet")
        provider_type: Optional provider type override (e.g. "openai" for OpenAI-compatible APIs)

    Returns:
        Route model id

    Examples:
        >>> to_route_model_id("openai", "gpt-4o")
        "gpt-4o"
        >>> to_route_model_id("anthropic", "claude-3-sonnet")
        "anthropic/claude-3-sonnet"
        >>> to_route_model_id("qwencoding", "qwen-max", "openai")
        "openai/qwen-max"
    """
    model_lower = model.lower()

    if model_lower.startswith("xiaomi_mimo/"):
        return model

    effective = provider_type or provider
    prefix = route_prefix_for_effective(effective)

    if prefix and model.startswith(prefix):
        return model

    return f"{prefix}{model}"


def parse_route_model_id(model_name: str) -> tuple[str, str]:
    """Parse a route model id into (provider, model).

    Args:
        model_name: Route model id (e.g. "openai/gpt-4o", "gpt-4o")

    Returns:
        Tuple of (provider, model). Bare model names are assumed to be OpenAI.

    Examples:
        >>> parse_route_model_id("openai/gpt-4o")
        ("openai", "gpt-4o")
        >>> parse_route_model_id("anthropic/claude-3-sonnet")
        ("anthropic", "claude-3-sonnet")
        >>> parse_route_model_id("gpt-4o")
        ("openai", "gpt-4o")
    """
    if "/" in model_name:
        parts = model_name.split("/", 1)
        return parts[0], parts[1]
    return "openai", model_name


__all__ = [
    "parse_route_model_id",
    "to_route_model_id",
]
