"""Which endpoint a call really needs, whatever wire is configured."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.config.wire import WireProtocol
from myrm_agent_harness.toolkits.llms.adapters.wire.routing import resolve_wire

Params = dict[str, object]

_TOOLS = [{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}]
_SELF_HOSTED = "http://localhost:8000/v1"
_AZURE = "https://resource.openai.azure.com"

_CASES: list[tuple[str, WireProtocol, Params, WireProtocol]] = [
    (
        "anthropic wire is a choice, never moved",
        "anthropic_messages",
        {"model": "openai/gpt-5-pro"},
        "anthropic_messages",
    ),
    ("unknown provider keeps the configured wire", "chat_completions", {"model": "mystery/model"}, "chat_completions"),
    ("unknown provider keeps responses too", "responses", {"model": "mystery/model"}, "responses"),
    ("no Responses endpoint means chat", "responses", {"model": "deepseek/deepseek-chat"}, "chat_completions"),
    ("configured responses is honoured", "responses", {"model": "openai/gpt-4o"}, "responses"),
    ("configured chat is honoured", "chat_completions", {"model": "openai/gpt-4o"}, "chat_completions"),
    ("catalog lists the model as responses-only", "chat_completions", {"model": "openai/gpt-5-pro"}, "responses"),
    (
        "xai native search needs responses",
        "chat_completions",
        {"model": "xai/grok-4", "web_search_options": {"search_context_size": "low"}},
        "responses",
    ),
    ("xai without search stays on chat", "chat_completions", {"model": "xai/grok-4"}, "chat_completions"),
    (
        "gpt-5.4 function tools on OpenAI itself",
        "chat_completions",
        {"model": "openai/gpt-5.4", "tools": _TOOLS},
        "responses",
    ),
    (
        "gpt-5.4 function tools with reasoning off are fine on chat",
        "chat_completions",
        {"model": "openai/gpt-5.4", "tools": _TOOLS, "reasoning_effort": "none"},
        "chat_completions",
    ),
    (
        "gpt-5.4 without tools stays on chat",
        "chat_completions",
        {"model": "openai/gpt-5.4"},
        "chat_completions",
    ),
    (
        "gpt-5.4 with only built-in tools stays on chat",
        "chat_completions",
        {"model": "openai/gpt-5.4", "tools": [{"type": "web_search"}]},
        "chat_completions",
    ),
    (
        "self-hosted gpt-5.4 serves function tools without reasoning",
        "chat_completions",
        {"model": "openai/gpt-5.4", "tools": _TOOLS, "api_base": _SELF_HOSTED},
        "chat_completions",
    ),
    (
        "self-hosted gpt-5.4 with active reasoning needs responses",
        "chat_completions",
        {"model": "openai/gpt-5.4", "tools": _TOOLS, "api_base": _SELF_HOSTED, "reasoning_effort": "low"},
        "responses",
    ),
    (
        "gpt-5.2 predates the restriction",
        "chat_completions",
        {"model": "openai/gpt-5.2", "tools": _TOOLS},
        "chat_completions",
    ),
    (
        "gpt-5 search models live on chat",
        "chat_completions",
        {"model": "openai/gpt-5.4-search-preview", "tools": _TOOLS},
        "chat_completions",
    ),
    (
        "azure enforces the restriction wherever it is hosted",
        "chat_completions",
        {"model": "azure/gpt-5.4", "tools": _TOOLS, "api_base": _AZURE},
        "responses",
    ),
]


@pytest.mark.parametrize(
    ("configured", "params", "expected"),
    [pytest.param(configured, params, expected, id=name) for name, configured, params, expected in _CASES],
)
def test_the_endpoint_a_call_uses(configured: WireProtocol, params: Params, expected: WireProtocol) -> None:
    assert resolve_wire(configured, params) == expected


def test_a_blank_model_or_provider_never_crashes_the_decision() -> None:
    assert resolve_wire("chat_completions", {"model": "", "custom_llm_provider": ""}) == "chat_completions"
