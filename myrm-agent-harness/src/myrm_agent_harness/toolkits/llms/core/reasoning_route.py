"""Provider-aware identity of a model call for reasoning-parameter normalization.

[INPUT]
- transport.profile::resolve_route (POS: provider, bare model id and endpoint of one call)

[OUTPUT]
- ReasoningRoute: provider profile id, bare lowercase model id, first-party endpoint flag, OpenAI-shaped body flag
- resolve_reasoning_route(): the ReasoningRoute of a model id, or None when no provider can be resolved

[POS]
The leading segment of a model id (``openai/``, ``azure/``) names the wire protocol a call speaks, not the model
family: SiliconFlow, OpenCode Go, NVIDIA and custom endpoints reach their own models through the ``openai/``
segment. Reasoning-parameter rules therefore read the bare model id together with whether the endpoint is the
provider's own, the same facts the wire router uses, instead of matching the route string.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.llms.transport import UnsupportedProviderError, resolve_route

_OPENAI_BODY_WIRES = frozenset({"openai_chat", "azure_openai"})


@dataclass(frozen=True, slots=True)
class ReasoningRoute:
    """What one model call resolves to, as far as reasoning parameters are concerned."""

    provider: str
    model: str
    first_party: bool
    openai_body: bool


def resolve_reasoning_route(
    model: str,
    base_url: str | None = None,
    custom_llm_provider: str | None = None,
) -> ReasoningRoute | None:
    """Resolve ``model`` to its provider, bare model id and endpoint kind; None when it names no provider."""
    try:
        route = resolve_route(model, custom_llm_provider=custom_llm_provider, api_base=base_url)
    except UnsupportedProviderError:
        return None
    return ReasoningRoute(
        provider=route.profile.id,
        model=route.model.lower(),
        first_party=route.base_url == route.profile.base_url,
        openai_body=route.profile.wire in _OPENAI_BODY_WIRES,
    )
