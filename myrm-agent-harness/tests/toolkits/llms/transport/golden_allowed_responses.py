"""Registered differences, section: the Responses wire.

[INPUT]
- golden_allowed_types (POS: AllowedDiff, the provider groups and the predicates the rules use)

[OUTPUT]
- RESPONSES_RULES: the rules of this section, in registry order

[POS]
The Responses wire: the adapter translates messages and tools itself; the baseline library bridged inside itself.
Assembled with the other sections into ``golden_allowed.RULES``; each rule states why the difference is wanted.
"""

from __future__ import annotations

from .golden_allowed_types import AllowedDiff

RESPONSES_RULES: tuple[AllowedDiff, ...] = (
    # --- Responses wire: adapter translation, not the baseline library's bridge ------------------------------------
    AllowedDiff(
        "responses-instructions",
        "The system prompt is sent as Responses `instructions`; the baseline library turned a `developer` prompt into a "
        "user-role input message.",
        "+",
        r"/body/instructions",
        providers=("openai_gpt5", "xai"),
    ),
    AllowedDiff(
        "responses-input-reshaped",
        "The input items follow the adapter's translation (flat role/content items, `instructions` split off).",
        "~",
        r"/body/input",
        providers=("openai_gpt5", "xai"),
    ),
    AllowedDiff(
        "responses-input-item-fields",
        "Input items omit the optional `type: message` and the default image `detail`.",
        "-",
        r"/body/input\[\d+\](/type|/content\[\d+\]/detail)",
        providers=("xai",),
    ),
    AllowedDiff(
        "xai-search-tools",
        "xAI native search is a `web_search` tool on the Responses endpoint, as in the baseline; tool items carry no "
        "`strict: null`.",
        "-",
        r"/body/tools(\[\d+\]/strict)?",
        providers=("xai",),
    ),
    AllowedDiff(
        "xai-search-tools-reshaped",
        "The tool list of the xAI search request in the adapter's Responses translation.",
        "~",
        r"/body/tools",
        providers=("xai",),
    ),
    AllowedDiff(
        "xai-search-tools-added",
        "The `web_search` tool appended to the tool list on the Responses endpoint.",
        "+",
        r"/body/tools",
        providers=("xai",),
    ),
    AllowedDiff(
        "responses-parallel-tool-calls",
        "`parallel_tool_calls` is forwarded on the Responses wire, as it is on chat completions.",
        "+",
        r"/body/parallel_tool_calls",
        providers=("openai", "openai_gpt5", "openai_like", "openrouter", "xai", "deepseek"),
    ),
    AllowedDiff(
        "responses-stream-flag",
        "A streaming Responses request to a custom endpoint states `stream: true`; the baseline library left the field out.",
        "+",
        r"/body/stream",
        providers=("openai_like",),
        scenarios=("responses_stream",),
    ),
    AllowedDiff(
        "responses-chat-fallback",
        "DeepSeek has no Responses endpoint: a Responses configuration falls back to chat completions with the "
        "adapter's own message conversion (the baseline library bridged inside itself).",
        "~",
        r"/body/(max_tokens|messages\[\d+\]/content)",
        providers=("deepseek",),
        scenarios=("responses", "responses_stream", "responses_tools"),
    ),
    AllowedDiff(
        "responses-chat-fallback-fields",
        "Fields of the chat request after the Responses-to-chat fallback (reasoning stamp, tool index, schema).",
        "+",
        r"/body/(messages\[\d+\]/reasoning_content|parallel_tool_calls)",
        providers=("deepseek",),
        scenarios=("responses_tools",),
    ),
    AllowedDiff(
        "responses-chat-fallback-removed",
        "Fields only the baseline library's bridge produced (empty tool list, per-call tool index, strict flag).",
        "-",
        r"/body/(tools|messages\[\d+\]/tool_calls\[\d+\]/index|tools\[\d+\]/function/strict)",
        providers=("deepseek",),
        scenarios=("responses", "responses_stream", "responses_tools"),
    ),
)
