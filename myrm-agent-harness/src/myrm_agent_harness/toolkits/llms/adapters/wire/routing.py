"""Effective wire protocol of one model call.

[INPUT]
- core.config.wire (POS: WireProtocol, the configured protocol)
- transport (POS: route resolution and provider profiles)
- catalog (POS: per-model endpoint mode)

[OUTPUT]
- resolve_wire: the protocol a call must use, given the configured one and the call's parameters

[POS]
The configured protocol is a preference; the provider and model decide what actually works. A model the catalog
lists as Responses-only, xAI's native search, and the GPT-5.4+ combination of function tools with reasoning are
served only by the Responses endpoint, so those calls move there even when chat completions is configured. A
Responses call to a provider without that endpoint falls back to chat completions, which every provider has.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.core.config.wire import WireProtocol
from myrm_agent_harness.toolkits.llms.catalog import model_info
from myrm_agent_harness.toolkits.llms.transport import Route, UnsupportedProviderError, resolve_route

_GPT_5_MINOR: Final = re.compile(r"^gpt-5\.(\d+)", re.IGNORECASE)
_GPT_5_SEARCH: Final = re.compile(r"gpt-5.*search", re.IGNORECASE)


def _is_gpt_5_4_plus(model: str) -> bool:
    match = _GPT_5_MINOR.match(model)
    return match is not None and int(match[1]) >= 4


def _has_function_tool(tools: object) -> bool:
    return isinstance(tools, list) and any(isinstance(t, Mapping) and t.get("type") == "function" for t in tools)


def _needs_responses(route: Route, params: Mapping[str, object]) -> bool:
    info = model_info(route.model, route.profile.id)
    if info is not None and info.get("mode") == "responses":
        return True
    if route.profile.id == "xai" and params.get("web_search_options") is not None:
        return True
    if route.profile.id not in ("openai", "azure") or _GPT_5_SEARCH.search(route.model):
        return False
    # Chat completions refuses function tools next to active reasoning on these models. It is enforced by
    # OpenAI itself and Azure; a self-hosted endpoint behind the `openai/` prefix serves them without reasoning.
    effort = params.get("reasoning_effort")
    enforcing = route.profile.id == "azure" or route.base_url == route.profile.base_url
    return bool(
        _is_gpt_5_4_plus(route.model)
        and _has_function_tool(params.get("tools"))
        and effort != "none"
        and (effort is not None or enforcing)
    )


def resolve_wire(configured: WireProtocol, params: Mapping[str, object]) -> WireProtocol:
    """The wire to call with; ``params`` carry the model, provider, endpoint and generation parameters."""
    if configured == "anthropic_messages":
        return configured
    try:
        route = resolve_route(
            str(params.get("model") or ""),
            custom_llm_provider=_text(params.get("custom_llm_provider")),
            api_base=_text(params.get("api_base")),
        )
    except UnsupportedProviderError:
        return configured  # the call itself reports the unreachable provider
    if not route.profile.responses:
        return "chat_completions"
    if configured == "responses" or _needs_responses(route, params):
        return "responses"
    return "chat_completions"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
