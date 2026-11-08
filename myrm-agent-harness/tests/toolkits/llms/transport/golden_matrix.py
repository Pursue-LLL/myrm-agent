"""The scenario matrix of the golden request capture: which providers, model families and scenarios are replayed.

[INPUT]
- (none) Pure data.

[OUTPUT]
- PROVIDERS / VARIANTS / BEDROCK_VARIANTS: provider key -> (model id as the settings layer builds it, factory kwargs)
- *_PROVIDERS / *_SCENARIOS: which scenarios run for which providers
- TOOLS / JSON_SCHEMA / BASE_URL / CHOICE_OF_SCENARIO / TOOL_SCENARIOS / HISTORY_SCENARIOS / EFFORT_OF_SCENARIO /
  FOREIGN_CALL_ID: what a scenario sends
- case_keys / case_name: every case in matrix order, and a case's key in the baseline

[POS]
The matrix has three parts: every provider against the base scenarios (plus the Responses and Anthropic-wire ones
where the provider has them), one model of each capability family that changes how a request is built (``VARIANTS``:
sampling parameters, reasoning effort, tool-call history), and requests the providers' APIs are strict about
(``EDGE_SCENARIOS``: blank text, parallel tool results, a closing assistant message, an image in a tool result, JSON
output beside tools). The committed baselines are keyed by ``case_name``, so a case is never renamed.
"""

from __future__ import annotations

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }
]
JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "r",
        "schema": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
    },
}
BASE_URL = "http://golden.invalid/v1"

# provider key -> (model id as the settings layer builds it, extra factory kwargs)
PROVIDERS: dict[str, tuple[str, dict[str, object]]] = {
    "openai": ("openai/gpt-4o-mini", {}),
    "openai_gpt5": ("openai/gpt-5", {}),
    "openai_o3": ("openai/o3", {}),
    "anthropic": ("anthropic/claude-sonnet-4-5", {}),
    "gemini": ("gemini/gemini-2.5-flash", {}),
    "deepseek": ("deepseek/deepseek-chat", {}),
    "deepseek_reasoner": ("deepseek/deepseek-reasoner", {}),
    "openrouter": ("openrouter/anthropic/claude-sonnet-4.5", {}),
    "zai": ("zai/glm-4.6", {}),
    "xai": ("xai/grok-4", {}),
    "ollama": ("ollama/llama3.1", {}),
    "moonshot": ("moonshot/kimi-k2-0905-preview", {}),
    "lm_studio": ("lm_studio/qwen2.5", {}),
    "mistral": ("mistral/mistral-large-latest", {}),
    "together_ai": ("together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", {}),
    "volcengine": ("volcengine/doubao-seed-1-6", {}),
    "fireworks_ai": ("fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct", {}),
    "minimax": ("minimax/MiniMax-M2", {}),
    "groq": ("groq/llama-3.3-70b-versatile", {}),
    "dashscope": ("dashscope/qwen-plus", {}),
    "azure": ("azure/gpt-4o", {"model_kwargs": {"api_version": "2024-10-21"}}),
    "perplexity": ("perplexity/sonar", {}),
    "cohere_chat": ("cohere_chat/command-r-plus", {}),
    "bedrock": ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", {}),
    "cerebras": ("cerebras/llama3.1-8b", {}),
    "xiaomi_mimo": ("xiaomi_mimo/mimo-v2-flash", {}),
    "yunshu": ("yunshu/gpt-4o-mini", {}),
    "openai_like": ("openai/some-model", {}),  # gateways reached through an api_base only
    "gemini_like": ("gemini/gemini-2.5-pro", {}),
    "anthropic_like": ("anthropic/claude-sonnet-4-5", {}),
}
# One model of each capability family that changes how a request is built (sampling parameters, reasoning effort,
# tool-call history). They share their provider's endpoint, so only the scenarios those rules touch are run.
VARIANTS: dict[str, tuple[str, dict[str, object]]] = {
    "anthropic_opus45": ("anthropic/claude-opus-4-5", {}),
    "anthropic_sonnet46": ("anthropic/claude-sonnet-4-6", {}),
    "anthropic_opus47": ("anthropic/claude-opus-4-7", {}),
    "anthropic_haiku45": ("anthropic/claude-haiku-4-5", {}),
    "gemini25pro": ("gemini/gemini-2.5-pro", {}),
    "gemini25flashlite": ("gemini/gemini-2.5-flash-lite", {}),
    "gemini3": ("gemini/gemini-3-pro-preview", {}),
    "gemini31": ("gemini/gemini-3.1-pro-preview", {}),
    "gemini3flash": ("gemini/gemini-3-flash-preview", {}),
    "openai_gpt51": ("openai/gpt-5.1", {}),
    "openai_gpt52": ("openai/gpt-5.2", {}),
}
PROVIDERS.update(VARIANTS)
# One model of each Bedrock family that builds its request differently: whether it takes tools and a tool choice,
# how it reasons, whether it has a native structured-output format, which sampling fields it reads. They share the
# ``bedrock`` provider's endpoint and run ``BEDROCK_SCENARIOS``.
BEDROCK_VARIANTS: dict[str, tuple[str, dict[str, object]]] = {
    "bedrock_claude35": ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", {}),
    "bedrock_claude37": ("bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0", {}),
    "bedrock_claude45": ("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", {}),
    "bedrock_haiku45": ("bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0", {}),
    "bedrock_opus45": ("bedrock/us.anthropic.claude-opus-4-5-20251101-v1:0", {}),
    "bedrock_sonnet46": ("bedrock/us.anthropic.claude-sonnet-4-6", {}),
    "bedrock_opus47": ("bedrock/us.anthropic.claude-opus-4-7", {}),
    "bedrock_nova": ("bedrock/amazon.nova-pro-v1:0", {}),
    "bedrock_nova2": ("bedrock/us.amazon.nova-2-lite-v1:0", {}),
    "bedrock_gptoss": ("bedrock/openai.gpt-oss-120b-1:0", {}),
    "bedrock_llama33": ("bedrock/us.meta.llama3-3-70b-instruct-v1:0", {}),
    "bedrock_llama3": ("bedrock/meta.llama3-70b-instruct-v1:0", {}),
    "bedrock_mistral": ("bedrock/mistral.mistral-large-2407-v1:0", {}),
    "bedrock_deepseek": ("bedrock/us.deepseek.r1-v1:0", {}),
    "bedrock_arn": ("bedrock/arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123", {}),
}
PROVIDERS.update(BEDROCK_VARIANTS)
# Reasoning efforts other than the base matrix's ``high``: how each maps to a budget, a level or a switch-off differs
# by model, so every variant and one model of each other reasoning family run them.
EFFORT_SCENARIOS = ("reasoning_minimal", "reasoning_medium", "reasoning_none")
EFFORT_PROVIDERS = frozenset({"anthropic", "gemini", "openai_gpt5", "openai_o3", "deepseek", "deepseek_reasoner"})
EFFORT_OF_SCENARIO = {
    "reasoning_high": "high",
    "reasoning_tools": "high",
    "reasoning_required": "high",
    "reasoning_xhigh": "xhigh",
    "reasoning_minimal": "minimal",
    "reasoning_medium": "medium",
    "reasoning_none": "none",
    "json_schema_reasoning": "high",
    "tools_json_reasoning": "high",
}
VARIANT_SCENARIOS = (
    "basic",
    "defaults",
    "sampling",
    "tools",
    "reasoning_high",
    "reasoning_xhigh",
    *EFFORT_SCENARIOS,
    "stream",
    "tool_history",
    "tool_history_unbound",
    "tool_history_foreign_ids",
    "reasoning_tools",
)
# What a Bedrock family changes: the tool choice (stated, forced, named), a forced choice beside reasoning, the
# structured answer alone and beside tools with and without reasoning, the caller's extra fields and cache marks.
BEDROCK_SCENARIOS = (
    *VARIANT_SCENARIOS,
    "tools_required",
    "tools_named",
    "reasoning_required",
    "json_schema",
    "tools_json_output",
    "json_schema_reasoning",
    "tools_json_reasoning",
    "extra_body",
    "cache_control",
)
BASE_SCENARIOS = (
    "basic",
    "defaults",
    "sampling",
    "tools",
    "reasoning_high",
    "json_schema",
    "extra_body",
    "image",
    "headers",
    "stream",
    "tool_history",
    "cache_control",
    "reasoning_tools",
)
# Requests the providers' APIs are strict about: blank text, parallel tool results, a closing assistant message, an
# image in a tool result, JSON output beside tools. Run on one provider per message translation (OpenAI-compatible,
# Anthropic, Gemini, Ollama) at its default endpoint.
EDGE_PROVIDERS = frozenset({"openai", "deepseek", "anthropic", "anthropic_opus47", "gemini", "gemini3", "ollama"})
EDGE_SCENARIOS = (
    "history_blank_assistant",
    "history_blank_assistant_tool",
    "history_blank_user",
    "history_parallel_tools",
    "history_prefill_space",
    "history_empty_tool_result",
    "history_tool_image",
    "tools_json_output",
)
RESPONSES_PROVIDERS = frozenset({"openai", "openai_gpt5", "openai_like", "xai", "deepseek", "openrouter"})
RESPONSES_SCENARIOS = ("responses", "responses_stream", "responses_tools")
ANTHROPIC_WIRE_PROVIDERS = frozenset({"openai_like"})
ANTHROPIC_WIRE_SCENARIOS = ("anthropic_wire", "anthropic_wire_stream", "anthropic_wire_tools")
# Scenarios that state a tool choice other than ``auto`` on a fresh conversation (no replayed tool call).
CHOICE_OF_SCENARIO: dict[str, str | dict[str, object]] = {
    "tools_required": "required",
    "tools_named": {"type": "function", "function": {"name": "get_weather"}},
    "reasoning_required": "required",
}
TOOL_SCENARIOS = frozenset(
    {
        *CHOICE_OF_SCENARIO,
        "tools",
        "tool_history",
        "tool_history_foreign_ids",
        "reasoning_tools",
        "responses_tools",
        "anthropic_wire_tools",
        "history_blank_assistant_tool",
        "history_parallel_tools",
        "history_empty_tool_result",
        "history_tool_image",
        "tools_json_output",
        "tools_json_reasoning",
    }
)
# The history replays a tool call and its result; ``tool_history_unbound`` sends it without any tool definition.
HISTORY_SCENARIOS = TOOL_SCENARIOS - {"tools", "tools_json_reasoning", *CHOICE_OF_SCENARIO} | {"tool_history_unbound"}
# Tool-call ids another provider minted (Kimi style: dots and a colon), replayed into this provider.
FOREIGN_CALL_ID = "functions.get_weather:0"


def case_keys(only: frozenset[str] | None = None) -> list[tuple[str, bool, str]]:
    """(provider, with_base, scenario) of every case in matrix order."""
    keys: list[tuple[str, bool, str]] = []
    for provider in PROVIDERS:
        if only is not None and provider not in only:
            continue
        if provider in BEDROCK_VARIANTS:
            keys.extend((provider, False, scenario) for scenario in BEDROCK_SCENARIOS)
            continue
        if provider in VARIANTS:
            keys.extend((provider, False, scenario) for scenario in VARIANT_SCENARIOS)
            if provider in EDGE_PROVIDERS:
                keys.extend((provider, False, scenario) for scenario in EDGE_SCENARIOS)
            continue
        for with_base in (False, True):
            if provider == "openai_like" and not with_base:
                continue
            scenarios = list(BASE_SCENARIOS)
            if provider in EDGE_PROVIDERS and not with_base:
                scenarios += EDGE_SCENARIOS
            if provider in EFFORT_PROVIDERS and not with_base:
                scenarios += EFFORT_SCENARIOS
            if provider in RESPONSES_PROVIDERS:
                scenarios += RESPONSES_SCENARIOS
            if provider in ANTHROPIC_WIRE_PROVIDERS:
                scenarios += ANTHROPIC_WIRE_SCENARIOS
            keys.extend((provider, with_base, scenario) for scenario in scenarios)
    return keys


def case_name(provider: str, with_base: bool, scenario: str) -> str:
    return f"{provider}|{'custom_base' if with_base else 'default_base'}|{scenario}"
