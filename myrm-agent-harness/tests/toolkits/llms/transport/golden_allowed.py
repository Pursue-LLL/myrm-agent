"""Registry of every intentional difference between the previous client library's requests and the transport's.

[INPUT]
- (none) Pure data.

[OUTPUT]
- AllowedDiff: one registered difference (provider, kind of change, field, reason)
- RULES: the registry
- HIDDEN_FETCHES: URLs the previous library called on its own, outside the model call itself

[POS]
The golden request test fails on any difference that is not listed here, so replacing the client library cannot
silently change what reaches a provider. Each rule states why the difference is wanted: either the previous request
was invalid or unsafe for the provider (a defect), or the transport sends the same meaning in another valid form.
A rule that no longer matches anything fails the test too, so this list never keeps stale entries.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

# Calls the previous library made by itself while serving a model call (tokenizer downloads from a model hub,
# a configuration file fetched from a code-hosting site, Ollama's model-info lookup around an embedding call).
# The transport makes none of them. Matched as substrings of the request URL.
HIDDEN_FETCHES = ("huggingface.co", "raw.githubusercontent.com", "/api/show")

_GEMINI_2 = ("gemini", "gemini_like", "gemini25pro", "gemini25flashlite")
_GEMINI_3 = ("gemini3", "gemini31", "gemini3flash")
_GEMINI = (*_GEMINI_2, *_GEMINI_3)
_ANTHROPIC = (
    "anthropic",
    "anthropic_like",
    "anthropic_opus45",
    "anthropic_sonnet46",
    "anthropic_opus47",
    "anthropic_haiku45",
)
# Claude generations whose catalog entry flags the native web search tool (the previous library's map did not).
_NATIVE_SEARCH_CLAUDE = ("anthropic_sonnet46", "anthropic_opus47")


@dataclass(frozen=True, slots=True)
class AllowedDiff:
    id: str
    reason: str
    kind: str
    path: str  # regular expression matched against the whole field path
    providers: tuple[str, ...] | None = None
    scenarios: tuple[str, ...] | None = None
    when: Callable[..., bool] | None = None


def _contains(side: str, text: str) -> Callable[..., bool]:
    return lambda diff: text in str(getattr(diff, side))


class _Change(Protocol):
    old: object
    new: object


def _only_repair_turns(diff: _Change) -> bool:
    """Whether the current Gemini turns are the baseline's plus the model turns that keep a tool result and the user
    message after it apart (both sides arrive canonical: adjacent turns of one role already merged)."""
    if not isinstance(diff.new, list) or not isinstance(diff.old, list):
        return False
    placeholder = [{"text": "[The previous response was interrupted before it completed.]"}]
    kept: list[dict[str, object]] = []
    for turn in diff.new:
        if turn["parts"] == placeholder:
            continue
        if kept and kept[-1]["role"] == turn["role"]:
            kept[-1] = {**turn, "parts": [*kept[-1]["parts"], *turn["parts"]]}  # type: ignore[misc]
        else:
            kept.append(turn)
    return kept == diff.old


def _media_moved_beside(diff: _Change) -> bool:
    """Whether the current Gemini parts are the baseline's with the media nested in each function response moved out
    to parts beside it."""
    if not isinstance(diff.new, list) or not isinstance(diff.old, list):
        return False
    moved: list[dict[str, object]] = []
    for part in diff.old:
        response = part.get("functionResponse")
        if not isinstance(response, dict) or "parts" not in response:
            moved.append(part)
            continue
        moved.append({"functionResponse": {key: value for key, value in response.items() if key != "parts"}})
        moved.extend(response["parts"])
    return moved == diff.new


RULES: tuple[AllowedDiff, ...] = (
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
        providers=(*_ANTHROPIC, "azure", *_GEMINI),
    ),
    AllowedDiff(
        "anthropic-doubled-version-path",
        "An api_base that already ended in /v1 produced `/v1/v1/messages`.",
        "~",
        r"/url",
        providers=(*_ANTHROPIC, "openai_like"),
        when=_contains("old", "/v1/v1/messages"),
    ),
    AllowedDiff(
        "lm-studio-default-endpoint",
        "LM Studio and Yunshu without an api_base were sent to api.openai.com with the caller's key; the default is "
        "their own server.",
        "~",
        r"/url",
        providers=("lm_studio", "yunshu"),
        when=_contains("old", "api.openai.com"),
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
        providers=_ANTHROPIC,
    ),
    AllowedDiff(
        "anthropic-extra-body-merged",
        "The flat counterpart of `anthropic-extra-body-nested`.",
        "+",
        r"/body/foo",
        providers=_ANTHROPIC,
    ),
    AllowedDiff(
        "anthropic-thinking-sampling",
        "An explicit temperature was sent next to extended thinking, which the API rejects.",
        "-",
        r"/body/temperature",
        providers=_ANTHROPIC,
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
        providers=_NATIVE_SEARCH_CLAUDE,
        when=_contains("new", "web_search_20250305"),
    ),
    AllowedDiff(
        "anthropic-native-search-appended",
        "The native search tool next to the caller's tools, or in place of the placeholder tool a tool-call history "
        "needs when the request declares none (see `anthropic-native-search-added`).",
        "~",
        r"/body/tools(\[\d+\]/(name|type))?",
        providers=_NATIVE_SEARCH_CLAUDE,
        when=_contains("new", "web_search"),
    ),
    AllowedDiff(
        "anthropic-native-search-replaces-placeholder",
        "The placeholder tool's fields, absent from the native search tool that now makes the declaration.",
        "-",
        r"/body/tools\[\d+\]/(description|input_schema)",
        providers=_NATIVE_SEARCH_CLAUDE,
        scenarios=("tool_history_unbound",),
    ),
    AllowedDiff(
        "anthropic-empty-turn-placeholder",
        "A tool-only assistant turn carried an injected placeholder text block; the turn is valid without it.",
        "~",
        r"/body/messages\[\d+\]/content",
        providers=(*_ANTHROPIC, "openai_like"),
        when=_contains("old", "Empty message content sanitised"),
    ),
    AllowedDiff(
        "anthropic-blank-turn-dropped",
        "A blank assistant turn between two user messages carried an injected placeholder sentence; the turn is "
        "dropped and the two user messages merge (the API takes no blank text, and the sentence read as content).",
        "~",
        r"/body/messages",
        providers=_ANTHROPIC,
        scenarios=("history_blank_assistant",),
        when=_contains("old", "Empty message content sanitised"),
    ),
    AllowedDiff(
        "anthropic-blank-request-placeholder",
        "A request holding nothing but blank text gets the one-character placeholder the wire already uses when the "
        "history does not open with a user turn, instead of an injected instruction-like sentence.",
        "~",
        r"/body/messages\[\d+\]/content\[\d+\]/text",
        providers=_ANTHROPIC,
        scenarios=("history_blank_user",),
        when=_contains("old", "Empty message content sanitised"),
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
    # --- the same meaning in another valid form -------------------------------------------------------------------
    AllowedDiff(
        "gemini-body-leaks",
        "`reasoning_effort` (top level) and the raw `response_format` (inside generationConfig) leaked into the "
        "Gemini body, which has no such fields; thinking and structured output are expressed natively.",
        "-",
        r"/body/(reasoningEffort|generationConfig/responseFormat)",
        providers=_GEMINI,
    ),
    AllowedDiff(
        "sampling-options-misplaced",
        "`top_p` and `top_k` from the model configuration were written at the top level of the Gemini and Ollama "
        "bodies, where neither API reads them (Gemini rejects unknown fields); they now sit in `generationConfig` "
        "and `options`.",
        "-",
        r"/body/top(_(p|k)|[PK])",
        providers=(*_GEMINI, "ollama"),
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "gemini-sampling-native-fields",
        "The counterpart of `sampling-options-misplaced`: `topP` and `topK` in `generationConfig`.",
        "+",
        r"/body/generationConfig/top[PK]",
        providers=_GEMINI,
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "anthropic-sampling-sent",
        "`top_k` from the model configuration is sent to the Messages API, which reads it; the previous library "
        "dropped it without saying so. `top_p` stays unsent beside a temperature, which current Claude models "
        "refuse. Not exercised against a real Anthropic server.",
        "+",
        r"/body/top_k",
        providers=_ANTHROPIC,
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
        providers=_GEMINI_2,
        scenarios=("tools_json_output",),
    ),
    AllowedDiff(
        "gemini-user-message-after-tool-result",
        "A user message right after a tool result was sent as a second user turn, which the API refuses (turns must "
        "alternate) or, folded into the result's turn, which Gemini 3 reads as the result's continuation; a model "
        "turn now separates them.",
        "~",
        r"/body/contents",
        providers=_GEMINI,
        when=_only_repair_turns,
    ),
    AllowedDiff(
        "gemini-2-tool-result-media-beside",
        "Google documents media inside a function response for Gemini 3 and later only; the previous library nested "
        "it for every model. Earlier models now get it as parts beside the response in the same turn, the shape "
        "Google's own CLI sends. Not exercised against a real Gemini server.",
        "~",
        r"/body/contents\[\d+\]/parts",
        providers=_GEMINI_2,
        scenarios=("history_tool_image",),
        when=_media_moved_beside,
    ),
    AllowedDiff(
        "gemini-3-api-version",
        "Gemini 3 models are called on the stable-beta path (`v1beta`, which carries thinking levels, thought "
        "signatures and function-call ids); the previous library used the `v1alpha` path.",
        "~",
        r"/url",
        providers=_GEMINI_3,
        when=_contains("old", "/v1alpha/"),
    ),
    AllowedDiff(
        "gemini-3-default-temperature",
        "The previous library stated Gemini 3's default temperature (1.0) explicitly when the caller set none; the "
        "API applies the same default on its own.",
        "-",
        r"/body/generationConfig/temperature",
        providers=_GEMINI_3,
        scenarios=("defaults",),
        when=lambda diff: diff.old == 1.0,
    ),
    AllowedDiff(
        "gemini-xhigh-thinking-level",
        "`xhigh` is mapped to Gemini's highest thinking level (`high`), or to a token budget of 8192 on models that "
        "think by budget; the previous library dropped the effort it could not map and sent no thinking configuration.",
        "+",
        r"/body/generationConfig/thinkingConfig",
        providers=_GEMINI,
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
        "The bundled catalog is newer than the previous library's price map and states 65536 as the output ceiling of "
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
        "native v2 chat API; with a custom api_base the previous library sent the bare base URL without any path.",
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
        when=_contains("old", "/beta/"),
    ),
    AllowedDiff(
        "groq-native-json-schema",
        "A json_schema response format is sent natively; the previous library emulated it with a forced "
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
        "developer-role-first-party",
        "The adapter marks the instruction message of GPT-5 / o-series models with the `developer` role; the previous "
        "library rewrote it back to `system`. It now reaches api.openai.com as `developer`; gateways still get `system`.",
        "~",
        r"/body/messages\[\d+\]/role",
        providers=("openai_gpt5", "openai_gpt51", "openai_gpt52", "openai_o3"),
    ),
    # --- Responses wire: adapter translation replaces the previous library's bridge --------------------------------
    AllowedDiff(
        "responses-instructions",
        "The system prompt is sent as Responses `instructions`; before, a `developer` prompt became a user-role "
        "input message.",
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
        "xAI native search is a `web_search` tool on the Responses endpoint, as before; tool items carry no "
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
        "A streaming Responses request to a custom endpoint now states `stream: true`; before the field was missing.",
        "+",
        r"/body/stream",
        providers=("openai_like",),
        scenarios=("responses_stream",),
    ),
    AllowedDiff(
        "responses-chat-fallback",
        "DeepSeek has no Responses endpoint: a Responses configuration falls back to chat completions with the "
        "adapter's own message conversion (the previous library bridged inside itself).",
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
        "Fields only the previous library's bridge produced (empty tool list, per-call tool index, strict flag).",
        "-",
        r"/body/(tools|messages\[\d+\]/tool_calls\[\d+\]/index|tools\[\d+\]/function/strict)",
        providers=("deepseek",),
        scenarios=("responses", "responses_stream", "responses_tools"),
    ),
)
