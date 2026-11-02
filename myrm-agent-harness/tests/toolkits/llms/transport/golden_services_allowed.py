"""Registry of every intentional difference between the previous client library's service calls and the transport's.

[INPUT]
- golden_allowed (POS: AllowedDiff, the shape of one registered difference)

[OUTPUT]
- SERVICE_RULES: the registry for the embedding, rerank, image generation/edit and web-search paths

[POS]
Companion of ``golden_allowed`` for the non-chat services. Providers are named ``family/provider`` (for example
``embedding/ollama``) because the same provider key appears in several families. The golden services test fails on a
difference that is not listed here and on a rule that matches nothing, so each entry states why the difference is
wanted: the previous request was a defect, the transport sends the same meaning in another valid form, or the
previous library refused something the transport now attempts.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qsl

from .golden_allowed import AllowedDiff

_IMAGE_OPENAI_SDK = (
    "image/dall_e_2",
    "image/dall_e_3",
    "image/gpt_image_1",
    "image/openai_gpt_image",
    "image/openai_compat",
    "image/together_flux",
    "image/xai",
)
_SEARCH = (
    "search/perplexity",
    "search/tavily",
    "search/exa_ai",
    "search/parallel_ai",
    "search/google_pse",
    "search/dataforseo",
    "search/firecrawl",
    "search/searxng",
    "search/brave",
    "search/serper",
)


def _params(query: object, ignore: frozenset[str] = frozenset()) -> dict[str, str]:
    """Query parameters, with Python's ``True`` read as the JSON-style ``true`` the transport writes."""
    return {k: v.lower() if v in ("True", "False") else v for k, v in parse_qsl(str(query)) if k not in ignore}


def _same_params(*ignore: str) -> Callable[..., bool]:
    skipped = frozenset(ignore)
    return lambda diff: _params(diff.old, skipped) == _params(diff.new, skipped)


def _old_is(text: str) -> Callable[..., bool]:
    return lambda diff: text in str(diff.old)


def _counts(old: int, new: int) -> Callable[..., bool]:
    return lambda diff: (diff.old, diff.new) == (old, new)


def _status(old: str, new: str) -> Callable[..., bool]:
    return lambda diff: (diff.old, diff.new) == (old, new)


SERVICE_RULES: tuple[AllowedDiff, ...] = (
    # --- fingerprints of the previous client stack ----------------------------------------------------------------
    AllowedDiff(
        "sdk-fingerprint-headers",
        "The previous library called through the OpenAI Python SDK, which stamps its own client fingerprint (platform, "
        "runtime, package version, retry counter, read timeout) on every call. The transport has no SDK.",
        "-",
        r"/headers/x-stainless-[a-z-]+",
    ),
    AllowedDiff(
        "library-attribution-headers",
        "The previous library identified itself to OpenRouter as 'liteLLM' (litellm.ai) in its attribution headers.",
        "-",
        r"/headers/(http-referer|x-title)",
        providers=("embedding/openrouter",),
    ),
    # --- embeddings -----------------------------------------------------------------------------------------------
    AllowedDiff(
        "cohere-current-host",
        "api.cohere.ai is the legacy host of the same service; api.cohere.com is Cohere's current documented host.",
        "~",
        r"/url",
        providers=("embedding/cohere",),
        when=_old_is("api.cohere.ai"),
    ),
    AllowedDiff(
        "azure-embedding-stable-api-version",
        "The previous library defaulted to the 2025-02-01-preview API; the transport uses the stable 2024-10-21 "
        "version, the same default as its chat path.",
        "~",
        r"/query",
        providers=("embedding/azure",),
    ),
    AllowedDiff(
        "voyage-no-encoding-format",
        "Voyage defines `encoding_format` as null (float arrays) or base64, so the explicit 'float' is outside its "
        "documented values; omitting the field returns the same float vectors.",
        "-",
        r"/body/encoding_format",
        providers=("embedding/voyage",),
    ),
    AllowedDiff(
        "ollama-openai-endpoint",
        "Ollama serves the OpenAI-shaped `/v1/embeddings` next to its native `/api/embed`, so the transport uses one "
        "request shape for every OpenAI-compatible provider (and sends the optional bearer key, which the native call "
        "ignored). Not exercised against a real Ollama server.",
        "~",
        r"/url",
        providers=("embedding/ollama",),
        when=_old_is("/api/embed"),
    ),
    AllowedDiff(
        "ollama-openai-body",
        "The OpenAI-shaped Ollama call carries `encoding_format: float` and the optional bearer key.",
        "+",
        r"/body/encoding_format|/headers/authorization",
        providers=("embedding/ollama",),
    ),
    AllowedDiff(
        "lm-studio-default-endpoint",
        "Without an `api_base` the previous library failed with a 400 (no default endpoint); the transport defaults "
        "to LM Studio's local server `http://localhost:1234/v1`, as it does for chat.",
        "count",
        r"",
        providers=("embedding/lm_studio",),
        when=_counts(0, 1),
    ),
    AllowedDiff(
        "lm-studio-default-endpoint-result",
        "Consequence of `lm-studio-default-endpoint`: the call succeeds instead of failing with a 400.",
        "~",
        r"/result|/error",
        providers=("embedding/lm_studio",),
    ),
    # --- rerank ---------------------------------------------------------------------------------------------------
    AllowedDiff(
        "azure-ai-rerank-prefix",
        "The settings do not offer Azure AI rerank; the transport has no `azure_ai` provider, so the id is passed to "
        "the given `api_base` whole, where the previous library stripped the `azure_ai/` prefix.",
        "~",
        r"/body/model",
        providers=("rerank/azure_ai",),
    ),
    AllowedDiff(
        "cohere-rerank-base-path",
        "Given `api_base` is the endpoint root, the previous library appended Cohere's `/v2/rerank` to it "
        "(`.../v1/v2/rerank`); the transport appends `/rerank`, as it does for every other provider.",
        "~",
        r"/url",
        providers=("rerank/cohere",),
        when=_old_is("/v2/rerank"),
    ),
    AllowedDiff(
        "together-rerank-honours-base",
        "The previous library ignored `api_base` for Together rerank and called api.together.xyz, bypassing a "
        "configured gateway; the transport calls the configured endpoint.",
        "~",
        r"/url",
        providers=("rerank/together_ai",),
        when=_old_is("api.together.xyz"),
    ),
    # --- image generation and edit --------------------------------------------------------------------------------
    AllowedDiff(
        "image-style-only-dall-e-3",
        "`style` is an option of DALL-E 3 only; the previous library forwarded it to Together and xAI models that "
        "have no such option.",
        "-",
        r"/body/style",
        providers=("image/together_flux", "image/xai"),
    ),
    AllowedDiff(
        "minimax-image-count",
        "The previous provider code was written to send `n` but litellm never delivered it, so asking for several "
        "images produced one; the transport sends `n`.",
        "+",
        r"/body/n",
        providers=("image/minimax",),
    ),
    AllowedDiff(
        "imagen-default-size",
        "`imageSize: 1K` is every Gemini image model's default, and Imagen 3 does not document the field; the "
        "transport sends the field only when it changes the output.",
        "-",
        r"/body/parameters/imageSize",
        providers=("image/gemini_imagen",),
        when=_old_is("1K"),
    ),
    AllowedDiff(
        "image-no-sdk-retries",
        "The OpenAI SDK retried every failing call three times on its own and the generator retried twice on top "
        "(6 requests); the transport makes the generator's attempts only (2 requests). Fewer attempts against a "
        "provider that keeps failing.",
        "count",
        r"",
        providers=_IMAGE_OPENAI_SDK,
        scenarios=("server_error",),
        when=_counts(6, 2),
    ),
    AllowedDiff(
        "image-edit-refused-before-sending",
        "Image edit is offered for DALL-E 2 and GPT Image 1 only (`supports_edit`). For Gemini Imagen and Stability the "
        "previous library sent a request and then failed (IndexError, 'model isn't mapped'); the transport refuses "
        "before sending. Same failure kind (ImageGenerationError), one request fewer.",
        "count",
        r"",
        providers=("image/gemini_imagen", "image/stability"),
        scenarios=("edit", "edit_mask"),
        when=_counts(1, 0),
    ),
    AllowedDiff(
        "flux-settings-alias",
        "`flux/schnell` is offered by the settings but the previous library rejected it ('LLM Provider NOT "
        "provided'), so every call failed before sending; the transport maps it to Together's FLUX.1-schnell.",
        "count",
        r"",
        providers=("image/flux",),
    ),
    AllowedDiff(
        "flux-settings-alias-result",
        "Consequence of `flux-settings-alias`: the call succeeds instead of failing before any request.",
        "~",
        r"/result|/error",
        providers=("image/flux",),
    ),
    AllowedDiff(
        "image-edit-attempted-for-xai-together",
        "Image edit is not offered for xAI or Together (`supports_edit` is false) and the previous library refused it "
        "up front ('image edit is not supported'); called directly, the transport sends an OpenAI-compatible "
        "`/images/edits` request and reports whatever the provider answers.",
        "count",
        r"",
        providers=("image/xai", "image/together_flux"),
        scenarios=("edit", "edit_mask"),
        when=_counts(0, 1),
    ),
    AllowedDiff(
        "image-edit-attempted-for-xai-together-result",
        "Consequence of `image-edit-attempted-for-xai-together`: the answer is read instead of a refusal.",
        "~",
        r"/result|/error",
        providers=("image/xai", "image/together_flux"),
        scenarios=("edit", "edit_mask"),
    ),
    # --- web search -----------------------------------------------------------------------------------------------
    AllowedDiff(
        "search-same-query-parameters",
        "The same query parameters in another order, with `true` where the previous library wrote Python's `True`.",
        "~",
        r"/query",
        providers=("search/brave", "search/google_pse"),
        when=_same_params(),
    ),
    AllowedDiff(
        "google-pse-no-engine-leak",
        "The previous library copied its `search_engine_id` argument into the query string as an extra parameter on "
        "top of the engine id `cx` that Google reads.",
        "~",
        r"/query",
        providers=("search/google_pse",),
        when=_same_params("search_engine_id"),
    ),
    AllowedDiff(
        "google-pse-gateway-key",
        "Behind a tool gateway the previous library sent the key from its environment variable and dropped the "
        "gateway token; the transport sends the gateway token the gateway authenticates.",
        "~",
        r"/query",
        providers=("search/google_pse",),
        scenarios=("gateway",),
        when=_same_params("search_engine_id", "key"),
    ),
    AllowedDiff(
        "search-provider-status-kept",
        "litellm turned every provider failure into a 500; the transport reports the provider's own status (401).",
        "~",
        r"/error",
        providers=_SEARCH,
        scenarios=("bad_key",),
        when=_status("failed:500", "failed:401"),
    ),
    AllowedDiff(
        "dataforseo-gateway-token-config-error",
        "A gateway token is not a DataForSEO `login:password` pair, so both stacks fail before sending anything: the "
        "previous library with a 500 ('DATAFORSEO_LOGIN is not set'), the transport with a configuration error that "
        "names the required key form.",
        "~",
        r"/error",
        providers=("search/dataforseo",),
        scenarios=("gateway",),
        when=_status("failed:500", "failed:None"),
    ),
    AllowedDiff(
        "search-rejected-key-surfaced",
        "For Brave, Google PSE and SearXNG the previous library swallowed a 401 and returned an empty result list, so "
        "a wrong key looked like 'no results'; the transport raises the failure.",
        "~",
        r"/error|/result",
        providers=("search/brave", "search/google_pse", "search/searxng"),
        scenarios=("bad_key",),
    ),
)
