"""Registered differences, section: the same meaning in another valid form.

[INPUT]
- golden_allowed_types (POS: AllowedDiff, the provider groups and the predicates the rules use)

[OUTPUT]
- EQUIVALENT_RULES: the rules of this section, in registry order

[POS]
A request that carries the same meaning in another valid form, or one the transport builds more correctly for the
provider. Assembled with the other sections into ``golden_allowed.RULES``; each rule states why the difference is
wanted.
"""

from __future__ import annotations

from .golden_allowed_types import (
    ANTHROPIC,
    GEMINI,
    GEMINI_2,
    GEMINI_3,
    AllowedDiff,
    contains,
    media_moved_beside,
    only_repair_turns,
)

EQUIVALENT_RULES: tuple[AllowedDiff, ...] = (
    # --- the same meaning in another valid form -------------------------------------------------------------------
    AllowedDiff(
        "gemini-body-leaks",
        "`reasoning_effort` (top level) and the raw `response_format` (inside generationConfig) leaked into the "
        "Gemini body, which has no such fields; thinking and structured output are expressed natively.",
        "-",
        r"/body/(reasoningEffort|generationConfig/responseFormat)",
        providers=GEMINI,
    ),
    AllowedDiff(
        "sampling-options-misplaced",
        "`top_p` and `top_k` from the model configuration were written at the top level of the Gemini and Ollama "
        "bodies, where neither API reads them (Gemini rejects unknown fields); they sit in `generationConfig` "
        "and `options`.",
        "-",
        r"/body/top(_(p|k)|[PK])",
        providers=(*GEMINI, "ollama"),
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "gemini-sampling-native-fields",
        "The counterpart of `sampling-options-misplaced`: `topP` and `topK` in `generationConfig`.",
        "+",
        r"/body/generationConfig/top[PK]",
        providers=GEMINI,
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "anthropic-sampling-sent",
        "`top_k` from the model configuration is sent to the Messages API, which reads it; the baseline library "
        "dropped it without saying so. `top_p` stays unsent beside a temperature, which current Claude models "
        "refuse. Not exercised against a real Anthropic server.",
        "+",
        r"/body/top_k",
        providers=ANTHROPIC,
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "cohere-stop-sequences-duplicate",
        "The native `stop_sequences` next to the OpenAI-style `stop` it duplicated; the compatibility endpoint takes "
        "`stop`.",
        "-",
        r"/body/stop_sequences",
        providers=("cohere_chat",),
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "gemini-2-json-output-beside-tools",
        "Models before Gemini 3 refuse JSON output next to function declarations; the tools stay and the JSON "
        "constraint is dropped, as the reference agents do. Not exercised against a real Gemini server.",
        "-",
        r"/body/generationConfig/(responseMimeType|responseJsonSchema)",
        providers=GEMINI_2,
        scenarios=("tools_json_output",),
    ),
    AllowedDiff(
        "gemini-user-message-after-tool-result",
        "A user message right after a tool result was sent as a second user turn, which the API refuses (turns must "
        "alternate) or, folded into the result's turn, which Gemini 3 reads as the result's continuation; a model "
        "turn separates them.",
        "~",
        r"/body/contents",
        providers=GEMINI,
        when=only_repair_turns,
    ),
    AllowedDiff(
        "gemini-2-tool-result-media-beside",
        "Google documents media inside a function response for Gemini 3 and later only; the baseline library nested "
        "it for every model. Earlier models get it as parts beside the response in the same turn, the shape "
        "Google's own CLI sends. Not exercised against a real Gemini server.",
        "~",
        r"/body/contents\[\d+\]/parts",
        providers=GEMINI_2,
        scenarios=("history_tool_image",),
        when=media_moved_beside,
    ),
    AllowedDiff(
        "gemini-3-api-version",
        "Gemini 3 models are called on the stable-beta path (`v1beta`, which carries thinking levels, thought "
        "signatures and function-call ids); the baseline library used the `v1alpha` path.",
        "~",
        r"/url",
        providers=GEMINI_3,
        when=contains("old", "/v1alpha/"),
    ),
    AllowedDiff(
        "gemini-3-default-temperature",
        "The baseline library stated Gemini 3's default temperature (1.0) explicitly when the caller set none; the "
        "API applies the same default on its own.",
        "-",
        r"/body/generationConfig/temperature",
        providers=GEMINI_3,
        scenarios=("defaults",),
        when=lambda diff: diff.old == 1.0,
    ),
    AllowedDiff(
        "gemini-xhigh-thinking-level",
        "`xhigh` is mapped to Gemini's highest thinking level (`high`), or to a token budget of 8192 on models that "
        "think by budget; the baseline library dropped the effort it could not map and sent no thinking configuration.",
        "+",
        r"/body/generationConfig/thinkingConfig",
        providers=GEMINI,
        scenarios=("reasoning_xhigh",),
    ),
    AllowedDiff(
        "gemini-pro-thinking-floor",
        "Gemini 2.5 Pro cannot switch thinking off and refuses a budget of 0; with the effort disabled the wire sends "
        "the model's floor (128). Not exercised against a real Gemini server.",
        "~",
        r"/body/generationConfig/thinkingConfig/thinkingBudget",
        providers=("gemini25pro",),
        scenarios=("reasoning_none",),
        when=lambda diff: (diff.old, diff.new) == (0, 128),
    ),
    AllowedDiff(
        "gemini-flash-ceiling-catalog",
        "The bundled catalog is newer than the baseline library's price map and states 65536 as the output ceiling of "
        "Gemini 2.5 Flash-Lite and 3 Flash (65535 there); the thinking headroom lifts a small cap to that ceiling "
        "for `xhigh`. Vertex refuses 65536 on the Flash-Lite line, which the output-cap recovery reads from the "
        "rejection and remembers.",
        "~",
        r"/body/generationConfig/maxOutputTokens",
        providers=("gemini25flashlite", "gemini3flash"),
        scenarios=("reasoning_xhigh",),
        when=lambda diff: (diff.old, diff.new) == (65535, 65536),
    ),
    AllowedDiff(
        "ollama-native-chat-api",
        "Ollama is called through its chat API (`/api/chat`, real roles, tools, options) instead of the legacy "
        "`/api/generate` prompt-concatenation endpoint that cannot carry tools or images properly.",
        "+",
        r"/body/(messages|tools|options/.*)",
        providers=("ollama",),
    ),
    AllowedDiff(
        "ollama-legacy-generate-fields",
        "The legacy `/api/generate` fields replaced by `ollama-native-chat-api`, and the leaked `reasoning_effort`.",
        "-",
        r"/body/(prompt|images|reasoning_effort)",
        providers=("ollama",),
    ),
    AllowedDiff(
        "ollama-endpoint",
        "`/api/generate` (and a doubled `/v1/api/generate` for a /v1 api_base) became `/api/chat`.",
        "~",
        r"/url",
        providers=("ollama",),
    ),
    AllowedDiff(
        "cohere-compatibility-endpoint",
        "Cohere is called through its OpenAI-compatible endpoint (`/compatibility/v1/chat/completions`) instead of the "
        "native v2 chat API; with a custom api_base the baseline library sent the bare base URL without any path.",
        "~",
        r"/url",
        providers=("cohere_chat",),
    ),
    AllowedDiff(
        "deepseek-standard-endpoint",
        "DeepSeek is called on its standard base URL instead of the `/beta` one (which exists for prefix completion and "
        "strict tool schemas, neither of which is used).",
        "~",
        r"/url",
        providers=("deepseek", "deepseek_reasoner"),
        when=contains("old", "/beta/"),
    ),
    AllowedDiff(
        "groq-native-json-schema",
        "A json_schema response format is sent natively; the baseline library emulated it with a forced "
        "`json_tool_call` function. A model without native support answers 400 and the caller's JSON-mode fallback applies.",
        "+",
        r"/body/response_format",
        providers=("groq",),
    ),
    AllowedDiff(
        "groq-json-schema-emulation",
        "The forced-function emulation replaced by `groq-native-json-schema`.",
        "-",
        r"/body/(tools|tool_choice)",
        providers=("groq",),
    ),
    AllowedDiff(
        "gateway-reasoning-effort-sent",
        "A reasoning effort set for a model behind an OpenAI-compatible gateway reaches the gateway: the `openai/` "
        "route prefix names the wire protocol, not the model family, so it does not decide whether a model takes the "
        "field. A gateway that rejects the field is retried without it and the rejection is remembered.",
        "+",
        r"/body/reasoning_effort",
        providers=("openai_like",),
        scenarios=("reasoning_high", "reasoning_tools"),
    ),
    AllowedDiff(
        "gateway-reasoning-output-headroom",
        "The thinking headroom (`max_tokens` floor for `high`) that goes with the reasoning effort "
        "`gateway-reasoning-effort-sent` lets through.",
        "~",
        r"/body/max_tokens",
        providers=("openai_like",),
        scenarios=("reasoning_high", "reasoning_tools"),
        when=lambda diff: (diff.old, diff.new) == (4096, 32768),
    ),
    AllowedDiff(
        "developer-role-first-party",
        "The adapter marks the instruction message of GPT-5 / o-series models with the `developer` role; the baseline "
        "library rewrote it back to `system`. It reaches api.openai.com as `developer`; gateways still get `system`.",
        "~",
        r"/body/messages\[\d+\]/role",
        providers=("openai_gpt5", "openai_gpt51", "openai_gpt52", "openai_o3"),
    ),
)
