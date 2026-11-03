# transport/

## Overview

Model transport: typed protocol wires over `httpx` that reach every LLM provider without a provider SDK or a
multi-provider client library. One facade (`LLMTransport`) resolves the provider route, lets the matching wire build the
request, executes it and hands the answer back in the OpenAI chat shape (dict, or an iterator of
`chat.completion.chunk` dicts), so the chat adapter above never sees a provider format. Five wires cover every provider
(OpenAI chat, Anthropic Messages, Gemini generateContent, Ollama chat, plus the OpenAI Responses wire); a provider that
speaks the OpenAI body is one data row in `profile.PROFILES`. The `provider/model` id is the persisted model format.

Embeddings, rerank and image generation use the same HTTP layer and credential rules through `service_routes.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Exports `LLMTransport`, `get_transport`, `Route`, `resolve_route`, `PROFILES`, error types | — |
| `client.py` | Core | `LLMTransport` facade: route -> wire `prepare` -> HTTP -> decoded answer; sync/async, chat and Responses | ✅ |
| `profile.py` | Config | `ProviderProfile` data table, `resolve_route`, `normalize_base_url`, `speaks_openai_body`; providers without a wire raise `UnsupportedProviderError` | ✅ |
| `params.py` | Core | `split_params`: transport options (credential, timeout, proxy, headers, `extra_body`) versus body parameters; `merge_headers` | ✅ |
| `http.py` | Core | Shared `httpx` clients per event loop (proxy- and TLS-policy aware, closed with `aclose_clients`), one retry on connect failure, SSE and NDJSON framing, `ProviderStream` that remembers the provider's own finish reason | ✅ |
| `errors.py` | Core | `LLMHTTPError` (status, parsed body, response), `LLMStreamError`; the attribute shape `errors.normalize` reads | ✅ |
| `openai_chat.py` | Core | OpenAI Chat Completions wire (also Azure and every OpenAI-compatible provider): request, parse and SSE decoder; the answer is the provider's own except that a top-level cache-read count (DeepSeek `prompt_cache_hit_tokens`, gateway `cache_read_input_tokens`) is also reported as `prompt_tokens_details.cached_tokens` | ✅ |
| `openai_responses.py` | Core | OpenAI Responses wire: routing and credential only, the adapter assembles the body | ✅ |
| `capabilities.py` | Core | What a model takes in a request: `claude_traits` (sampling parameters, adaptive thinking, `xhigh`/`max` effort, output ceiling), `keeps_temperature_without_reasoning`, and the Gemini generation checks (`gemini_from_3`, `gemini_thinks_by_level`: a version gate, not a name prefix); the catalog's flags first, the model name for ids the catalog does not list | ✅ |
| `anthropic_messages.py` | Core | Anthropic Messages wire request: content blocks, cache markers, tool-call history (id alphabet, placeholder tool), blank-text and prefill rules, sampling parameters per model generation, default `max_tokens` | ✅ |
| `anthropic_thinking.py` | Core | `request_thinking`: the `thinking` block and `output_config.effort` of a request (adaptive thinking with clamped effort, or a token budget); off when the replayed tool calls lack their signed thinking block | ✅ |
| `anthropic_response.py` | Core | Anthropic answer and event decoding into the chat shape, with cache accounting folded into the prompt total | ✅ |
| `anthropic_schema.py` | Core | Structured-output schema reduction to the subset the Messages API accepts | ✅ |
| `gemini_generate.py` | Core | Gemini generateContent wire: request (thinking budget before Gemini 3, thinking level from it and on the `-latest` aliases; JSON output left out where the API refuses it beside function declarations), answer and SSE decoding | ✅ |
| `gemini_contents.py` | Core | Chat history as alternating user/model `contents`: Gemini 3 and later call ids and `thoughtSignature` (carried in the tool-call id), media a tool returned (inside the function response on Gemini 3+, beside it elsewhere), a model turn kept between a tool result and a user message | ✅ |
| `gemini_schema.py` | Core | Tool-schema reduction to the Gemini subset | ✅ |
| `ollama_chat.py` | Core | Native Ollama `/api/chat` wire (tools, structured output, thinking) with NDJSON decoding | ✅ |
| `json_schema.py` | Core | `inline_refs`: local `$ref` inlining shared by the Anthropic and Gemini schema converters | ✅ |
| `service_routes.py` | Config | Endpoint and credential resolution for embedding, rerank and image providers | ✅ |
| `embeddings.py` | Core | OpenAI-compatible `/embeddings`, Cohere `/embed` and Gemini `:batchEmbedContents`; a custom `api_base` is a gateway that keeps the whole model id | ✅ |
| `rerank.py` | Core | `/rerank` for Cohere, Jina, Together, SiliconFlow, Voyage and compatible gateways | ✅ |
| `images.py` | Core | Image generation and editing: OpenAI-family, Gemini, Stability, MiniMax | ✅ |

## Key Dependencies

- `httpx` (HTTP, proxy and TLS behavior; `infra.tls_compat` supplies the trust store)
- `catalog` (model capability flags and output ceilings that decide what a request may carry)
- Consumed by `adapters/chat_model` (chat), `toolkits/retriever` (embeddings, rerank), `toolkits/llms/image` (images)

## Constraints

- A wire never mutates the caller's parameters. It leaves out a parameter the model is known to reject (the catalog
  states which, the model name covers ids the catalog does not list) and sends everything else as asked; any other
  rejection is the caller's decision (the gateway normalizer retries a 400 with the offending parameter stripped).
- What the API refuses is decided in the wire, not discovered by failing: blank text, tool-call ids outside the accepted
  alphabet, a history with tool calls but no tool definition (Anthropic) and adjacent same-role turns (Gemini) are
  repaired while the request is built.
- A credential is read from the call's own arguments or the provider's environment variables only; nothing is written
  to process-global state.
- Imports stay light: no provider SDK is loaded.
