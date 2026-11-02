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

# Calls the previous library made by itself while serving a model call (tokenizer downloads from a model hub,
# a configuration file fetched from a code-hosting site, Ollama's model-info lookup around an embedding call).
# The transport makes none of them. Matched as substrings of the request URL.
HIDDEN_FETCHES = ("huggingface.co", "raw.githubusercontent.com", "/api/show")

_GEMINI = ("gemini", "gemini_like")
_ANTHROPIC = ("anthropic", "anthropic_like")


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


RULES: tuple[AllowedDiff, ...] = (
    # --- defects of the previous request construction -------------------------------------------------------------
    AllowedDiff(
        "model-kwargs-leak",
        "The caller's `model_kwargs` container was copied into the provider body as an unknown top-level field.",
        "-",
        r"/body/model_kwargs",
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
        "gemini-json-names-old",
        "Gemini fields were written in snake_case; the transport writes the canonical camelCase (both are accepted).",
        "-",
        r"/body/(generationConfig/(max_output_tokens|response_json_schema|response_mime_type|frequency_penalty|stop_sequences)"
        r"|tools\[\d+\]/function_declarations|contents\[\d+\]/parts\[\d+\]/inline_data)",
        providers=_GEMINI,
    ),
    AllowedDiff(
        "gemini-json-names-new",
        "The camelCase counterpart of `gemini-json-names-old`.",
        "+",
        r"/body/(generationConfig/(maxOutputTokens|responseJsonSchema|responseMimeType|frequencyPenalty|stopSequences)"
        r"|tools\[\d+\]/functionDeclarations|contents\[\d+\]/parts\[\d+\]/inlineData)",
        providers=_GEMINI,
    ),
    AllowedDiff(
        "gemini-body-leaks",
        "`reasoning_effort` (top level) and the raw `response_format` (inside generationConfig) leaked into the "
        "Gemini body, which has no such fields; thinking and structured output are expressed natively.",
        "-",
        r"/body/(reasoning_effort|generationConfig/response_format)",
        providers=_GEMINI,
    ),
    AllowedDiff(
        "sampling-options-misplaced",
        "`top_p` and `top_k` from the model configuration were written at the top level of the Gemini and Ollama "
        "bodies, where neither API reads them (Gemini rejects unknown fields); they now sit in `generationConfig` "
        "and `options`.",
        "-",
        r"/body/top_(p|k)",
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
        "`top_p` and `top_k` from the model configuration are sent to the Messages API, which reads both; the "
        "previous library dropped them without saying so. A model that refuses `top_p` next to `temperature` is "
        "answered by the adapter's strip-and-retry. Not exercised against a real Anthropic server.",
        "+",
        r"/body/top_(p|k)",
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
        "gemini-empty-text-part",
        "A tool-calling model turn carried an empty text part; the turn is sent as its function call alone.",
        "~",
        r"/body/contents",
        providers=_GEMINI,
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
        providers=("openai_gpt5", "openai_o3"),
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
    # --- removed providers ----------------------------------------------------------------------------------------
    AllowedDiff(
        "bedrock-removed",
        "Bedrock is not reachable through the transport (it signs requests with AWS credentials); no request is made.",
        "count",
        r"",
        providers=("bedrock",),
    ),
)
