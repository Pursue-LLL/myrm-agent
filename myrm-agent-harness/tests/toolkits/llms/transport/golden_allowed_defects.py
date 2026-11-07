"""Registered differences, section: defects of the previous request construction.

[INPUT]
- golden_allowed_types (POS: AllowedDiff, the provider groups and the predicates the rules use)

[OUTPUT]
- DEFECT_RULES: the rules of this section, in registry order

[POS]
The previous request was invalid or unsafe for the provider: a leaked or misplaced field, a wrong endpoint, a
parameter the API refuses. Assembled with the other sections into ``golden_allowed.RULES``; each rule states why the
difference is wanted.
"""

from __future__ import annotations

from .golden_allowed_types import ANTHROPIC, GEMINI, NATIVE_SEARCH_CLAUDE, AllowedDiff, contains

DEFECT_RULES: tuple[AllowedDiff, ...] = (
    # --- defects of the previous request construction -------------------------------------------------------------
    AllowedDiff(
        "model-kwargs-leak",
        "The caller's `model_kwargs` container was copied into the provider body as an unknown top-level field.",
        "-",
        r"/body/model(_k|K)wargs",
    ),
    AllowedDiff(
        "stream-false-explicit",
        "`stream: false` (the default of every OpenAI-compatible API) was sent explicitly by some providers.",
        "-",
        r"/body/stream",
    ),
    AllowedDiff(
        "bearer-beside-vendor-key",
        "A bearer Authorization header was added next to the vendor's own key header (x-api-key, x-goog-api-key, "
        "api-key). It is now sent only to custom Anthropic hosts, where gateways expect it.",
        "-",
        r"/headers/authorization",
        providers=(*ANTHROPIC, "azure", *GEMINI),
    ),
    AllowedDiff(
        "anthropic-doubled-version-path",
        "An api_base that already ended in /v1 produced `/v1/v1/messages`.",
        "~",
        r"/url",
        providers=(*ANTHROPIC, "openai_like"),
        when=contains("old", "/v1/v1/messages"),
    ),
    AllowedDiff(
        "lm-studio-default-endpoint",
        "LM Studio and Yunshu without an api_base were sent to api.openai.com with the caller's key; the default is "
        "their own server.",
        "~",
        r"/url",
        providers=("lm_studio", "yunshu"),
        when=contains("old", "api.openai.com"),
    ),
    AllowedDiff(
        "sdk-fingerprint-headers",
        "Some calls of the previous library went through the OpenAI Python SDK, which stamps its own client "
        "fingerprint (platform, runtime, package version, retry counter, read timeout) on the request. The transport "
        "has no SDK.",
        "-",
        r"/headers/x-stainless-[a-z-]+",
    ),
    AllowedDiff(
        "thinking-floor-not-clamped-to-catalog",
        "With no budget set, a thinking model gets the 16384-token floor. The previous library then lowered it to the "
        "catalog's output ceiling (8192 for MiniMax-M2) without saying so; the transport sends the floor and, if the "
        "provider refuses it, learns the limit from the error and retries. Not exercised against a real MiniMax "
        "server.",
        "~",
        r"/body/max_tokens",
        providers=("minimax",),
        scenarios=("defaults",),
        when=lambda diff: (diff.old, diff.new) == (8192, 16384),
    ),
    AllowedDiff(
        "yunshu-output-limit",
        "`max_tokens` is capped at the model's catalog output limit (16384 for gpt-4o-mini); the previous library found "
        "no catalog entry under the `yunshu/` prefix and sent 32768, which the model would refuse.",
        "~",
        r"/body/max_tokens",
        providers=("yunshu",),
        scenarios=("reasoning_high", "reasoning_tools"),
    ),
    AllowedDiff(
        "anthropic-extra-body-nested",
        "`extra_body` was nested under an `extra_body` key, which the Messages API rejects; entries are merged flat.",
        "-",
        r"/body/extra_body",
        providers=ANTHROPIC,
    ),
    AllowedDiff(
        "anthropic-extra-body-merged",
        "The flat counterpart of `anthropic-extra-body-nested`.",
        "+",
        r"/body/foo",
        providers=ANTHROPIC,
    ),
    AllowedDiff(
        "anthropic-thinking-sampling",
        "An explicit temperature was sent next to extended thinking, which the API rejects.",
        "-",
        r"/body/temperature",
        providers=ANTHROPIC,
        scenarios=("reasoning_high", "reasoning_tools", "reasoning_xhigh", "reasoning_medium", "reasoning_minimal"),
    ),
    AllowedDiff(
        "anthropic-xhigh-unsupported-model",
        "Claude Sonnet 4.6 has no `xhigh` effort: the previous library refused the call before sending anything; the "
        "wire sends the highest level the model has (`max`).",
        "count",
        r"",
        providers=("anthropic_sonnet46",),
        scenarios=("reasoning_xhigh",),
    ),
    AllowedDiff(
        "anthropic-native-search-added",
        "The bundled catalog is newer than the previous library's price map and marks Claude Sonnet 4.6 / Opus 4.7 as "
        "offering the native web search tool; the model factory enables it for every model the catalog flags "
        "(`core/llm.py`), as it already did for GPT-5, Gemini and Grok.",
        "+",
        r"/body/tools",
        providers=NATIVE_SEARCH_CLAUDE,
        when=contains("new", "web_search_20250305"),
    ),
    AllowedDiff(
        "anthropic-native-search-appended",
        "The native search tool next to the caller's tools, or in place of the placeholder tool a tool-call history "
        "needs when the request declares none (see `anthropic-native-search-added`).",
        "~",
        r"/body/tools(\[\d+\]/(name|type))?",
        providers=NATIVE_SEARCH_CLAUDE,
        when=contains("new", "web_search"),
    ),
    AllowedDiff(
        "anthropic-native-search-replaces-placeholder",
        "The placeholder tool's fields, absent from the native search tool that now makes the declaration.",
        "-",
        r"/body/tools\[\d+\]/(description|input_schema)",
        providers=NATIVE_SEARCH_CLAUDE,
        scenarios=("tool_history_unbound",),
    ),
    AllowedDiff(
        "anthropic-empty-turn-placeholder",
        "A tool-only assistant turn carried an injected placeholder text block; the turn is valid without it.",
        "~",
        r"/body/messages\[\d+\]/content",
        providers=(*ANTHROPIC, "openai_like"),
        when=contains("old", "Empty message content sanitised"),
    ),
    AllowedDiff(
        "anthropic-blank-turn-dropped",
        "A blank assistant turn between two user messages carried an injected placeholder sentence; the turn is "
        "dropped and the two user messages merge (the API takes no blank text, and the sentence read as content).",
        "~",
        r"/body/messages",
        providers=ANTHROPIC,
        scenarios=("history_blank_assistant",),
        when=contains("old", "Empty message content sanitised"),
    ),
    AllowedDiff(
        "anthropic-blank-request-placeholder",
        "A request holding nothing but blank text gets the one-character placeholder the wire already uses when the "
        "history does not open with a user turn, instead of an injected instruction-like sentence.",
        "~",
        r"/body/messages\[\d+\]/content\[\d+\]/text",
        providers=ANTHROPIC,
        scenarios=("history_blank_user",),
        when=contains("old", "Empty message content sanitised"),
    ),
    AllowedDiff(
        "openai-only-field-in-anthropic-body",
        "`parallel_tool_calls` (an OpenAI field) leaked into an Anthropic request body.",
        "-",
        r"/body/parallel_tool_calls",
        providers=("openai_like",),
        scenarios=("anthropic_wire_tools",),
    ),
    AllowedDiff(
        "anthropic-wire-stream-options",
        "`stream_options` (an OpenAI field) leaked into an Anthropic streaming request body.",
        "-",
        r"/body/stream_options",
        providers=("openai_like",),
        scenarios=("anthropic_wire_stream",),
    ),
)
