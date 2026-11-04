# transport/

## Overview

Model transport: typed protocol wires over `httpx` that reach every LLM provider without a provider SDK or a
multi-provider client library. One facade (`LLMTransport`) resolves the provider route, lets the matching wire build the
request, executes it and hands the answer back in the OpenAI chat shape (dict, or an iterator of
`chat.completion.chunk` dicts), so the chat adapter above never sees a provider format. Six wires cover every supported
provider (OpenAI chat, Anthropic Messages, Gemini generateContent, Ollama chat, AWS Bedrock Converse, plus the OpenAI
Responses wire); a provider that speaks the OpenAI body is one data row in `profile.PROFILES`. A provider without a wire
(Replicate) raises `UnsupportedProviderError`. The `provider/model` id is the persisted model format.

Embeddings, rerank and image generation use the same HTTP layer through `service_routes.py`, with one difference: they
take a credential only from the caller, never from the environment.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Exports `LLMTransport`, `get_transport`, `Route`, `resolve_route`, `PROFILES`, error types | — |
| `client.py` | Core | `LLMTransport` facade: route -> wire `prepare` -> HTTP -> decoded answer, shaped once by `chat_shape` (chat completions and streams; the Responses wire is read by its adapter); a request already answered comes from `answer_cache`; sync/async | ✅ |
| `profile.py` | Config | `ProviderProfile` data table (default endpoint, credential variables `api_key_env`, endpoint variables `api_base_env`, Azure's `api_version_env`), `resolve_route` (the call's endpoint and key, else the provider's own variables, else the default endpoint), `first_env`, `normalize_base_url`, `speaks_openai_body`; providers without a wire raise `UnsupportedProviderError` | ✅ |
| `params.py` | Core | `split_params`: transport options (credential, timeout, proxy, headers, `extra_body`) versus body parameters; `merge_headers` | ✅ |
| `http.py` | Core | Shared `httpx` clients per event loop (proxy- and TLS-policy aware, closed with `aclose_clients`), the retry loop of a request that allows one (`PreparedRequest.retries`), `ProviderStream` that remembers the provider's own finish reason (`finish_reason_of` reads it off a chunk) | ✅ |
| `answer_cache.py` | Core | The process-wide answer cache: chat (plain and streamed), Responses, embedding and rerank answers are kept for an hour (200 entries, 1 MiB each, least recently used out first) under the identity of the request on the wire (endpoint, credentials, headers, body) and handed back as fresh copies; only an answer that finished normally and says something is kept, a stream is recorded by its decoder and filed when the provider ends it; `MYRM_LLM_ANSWER_CACHE=0` switches it off | ✅ |
| `retry.py` | Core | Retry policy of one request: 408/409/429/5xx answers and refused or dropped connections are retried twice (0.5 s doubling to 8 s with jitter, the provider's Retry-After or `retry-after-ms` honoured while it fits the 8 s ceiling, `x-should-retry` obeyed); a read or write timeout and a longer Retry-After are passed up at once; only for failures before the provider produced anything | ✅ |
| `errors.py` | Core | `LLMHTTPError` (status, parsed body, response); `LLMAnswerError` (a failure the provider sent inside a 2xx answer, carrying the status it stands for: `error_status`, MiniMax's `BASE_RESP_STATUS`); `LLMResponseError` (a 2xx answer that is not usable: not JSON, a stream frame cut off, no choice; reported as the 502 a gateway would); the attribute shape `errors.normalize` reads | ✅ |
| `stream_events.py` | Core | `iter_stream_events` / `aiter_stream_events`: a streamed body in any of its three framings (SSE, NDJSON, the binary AWS event stream with its CRC-32 checks) reduced to `(event, data)` pairs; an exception or error message of the event stream becomes an `exception:<type>` / `error:<code>` event; a corrupted or cut-off message fails the stream like a cut-off JSON frame | ✅ |
| `frames.py` | Core | `json_frame`: the JSON object one stream frame carries; text that does not open an object (keep-alive word, `[DONE]`, `[PING]`) is skipped, an object that does not parse raises `LLMResponseError` instead of dropping content; shared by every wire's decoder | ✅ |
| `chat_shape.py` | Core | The one pass that gives the adapter the shape it assumes: `shape_usage` (counts as ints, total filled), `FINISH_REASONS` (every provider's finish word onto OpenAI's, a tool call wins over `stop`), `shape_completion` (role, message, choices checked), `shape_chunk`, `ShapedDecoder` | ✅ |
| `openai_chat.py` | Core | OpenAI Chat Completions wire (also Azure and every OpenAI-compatible provider): request, parse and SSE decoder; the answer is the provider's own except that a top-level cache-read count (DeepSeek `prompt_cache_hit_tokens`, gateway `cache_read_input_tokens`) is also reported as `prompt_tokens_details.cached_tokens`, and a failure sent inside it (an `error` object, MiniMax `base_resp`, a cut-off finish reason: `error`, DeepSeek `insufficient_system_resource`/`aborted`) raises `LLMAnswerError` | ✅ |
| `openai_responses.py` | Core | OpenAI Responses wire: routing and credential only, the adapter assembles the body | ✅ |
| `capabilities.py` | Core | What a model takes in a request: `claude_traits` (sampling parameters, adaptive thinking, `xhigh`/`max` effort, output ceiling), `keeps_temperature_without_reasoning`, and the Gemini generation checks (`gemini_from_3`, `gemini_thinks_by_level`: a version gate, not a name prefix); the catalog's flags first, the model name for ids the catalog does not list | ✅ |
| `anthropic_messages.py` | Core | Anthropic Messages wire request: content blocks, cache markers, tool-call history (id alphabet, placeholder tool), blank-text and prefill rules, sampling parameters per model generation, default `max_tokens` | ✅ |
| `anthropic_thinking.py` | Core | `request_thinking`: the `thinking` block and `output_config.effort` of a request (adaptive thinking with clamped effort, or a token budget); off when the replayed tool calls lack their signed thinking block | ✅ |
| `anthropic_response.py` | Core | Anthropic answer and event decoding into the chat shape, with cache accounting folded into the prompt total; an `error` event raises `LLMAnswerError`; a response that filled the context window finishes as `length` | ✅ |
| `anthropic_schema.py` | Core | Structured-output schema reduction to the subset the Messages API accepts | ✅ |
| `gemini_generate.py` | Core | Gemini generateContent wire: request (thinking budget before Gemini 3, thinking level from it and on the `-latest` aliases; JSON output left out where the API refuses it beside function declarations), answer and SSE decoding | ✅ |
| `gemini_contents.py` | Core | Chat history as alternating user/model `contents`: Gemini 3 and later call ids and `thoughtSignature` (carried in the tool-call id), media a tool returned (inside the function response on Gemini 3+, beside it elsewhere), a model turn kept between a tool result and a user message | ✅ |
| `gemini_schema.py` | Core | Tool-schema reduction to the Gemini subset | ✅ |
| `bedrock_converse.py` | Core | Bedrock Converse wire request (`/model/{id}/converse` and `/converse-stream`, bearer API key, region from the ARN or the AWS variables): the caller's tools and tool choice sent as stated, thinking per model family (Claude block, Nova 2 `reasoningConfig`, gpt-oss effort; an opaque ARN is treated as Claude), `parallel_tool_calls` as `disable_parallel_tool_use` where the catalog lists it, `top_k` where the model takes one, placeholder tool for replayed tool calls, Nova grounding | ✅ |
| `bedrock_content.py` | Core | Chat history as strictly alternating Converse turns (merged neighbours, repaired tool-call ids, images and documents as bytes, cache points) and the reversible tool-name escape | ✅ |
| `bedrock_structured.py` | Core | Structured output on Bedrock: native `outputConfig.textFormat` for the models the catalog lists, otherwise one synthetic `json_tool_call` tool whose call is the answer | ✅ |
| `bedrock_response.py` | Core | Converse answer and event-stream decoding into the chat shape (reasoning and signed thinking blocks, tool calls, cache counters folded into the prompt total, the synthetic tool's call returned as text); an exception event raises `LLMAnswerError` with the status it stands for | ✅ |
| `ollama_chat.py` | Core | Native Ollama `/api/chat` wire (tools, structured output, thinking) with NDJSON decoding | ✅ |
| `json_schema.py` | Core | `inline_refs`: local `$ref` inlining shared by the Anthropic and Gemini schema converters | ✅ |
| `service_routes.py` | Config | Endpoint (the call's, else the provider's own variable, else its default) and credential (the call's only) resolution for embedding, rerank and image providers; `SERVICE_PROFILES` for the ones that serve no chat | ✅ |
| `embeddings.py` | Core | OpenAI-compatible `/embeddings`, Cohere `/embed` and Gemini `:batchEmbedContents`; a custom `api_base` is a gateway that keeps the whole model id | ✅ |
| `rerank.py` | Core | `/rerank` for Cohere, Jina, Together, SiliconFlow, Voyage and compatible gateways; an endpoint that stops short of a version segment gets the provider's (`/v2` Cohere, `/v1` Jina and Voyage) | ✅ |
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
  alphabet, a history with tool calls but no tool definition (Anthropic, Bedrock) and adjacent same-role turns (Gemini,
  Bedrock) are repaired while the request is built.
- A guess about what a model can do never withholds what the caller asked for: Bedrock models receive the tools and the
  tool choice the caller states, whether or not the catalog lists them, because a refusal from the API names the
  problem while a tool dropped silently makes an agent fail without a word.
- A chat call's endpoint, credential and (Azure) API version come from its own arguments, then the provider's own
  environment variables, then the provider's default; one provider's variable never redirects or authenticates another
  and nothing is written to process-global state. A service call (embedding, rerank, image) resolves its endpoint the
  same way but reads no credential from the environment: the key a settings screen stores is the only one it sends.
- A chat or Responses request retries what failed before the provider produced anything and never a stream that has begun;
  a provider silent for the whole request limit and a Retry-After beyond the 8 s backoff ceiling are passed up at once, so
  key rotation, failover and the agent's visible transient retry decide instead of the call blocking unseen; embeddings
  (their own retry in `CloudEmbedding`), rerank and media generation (billed, their own per-model retry) do not retry here.
- The adapter above reads plain dicts in OpenAI's shapes, so every chat answer is shaped once at the facade, whatever the
  wire or the gateway sent: token counts that are ints (a usage a provider leaves out stays empty; the call is still counted),
  a finish reason from OpenAI's five, a role, a message in every choice. A consumer carries no defence of its own.
- A failure is never read as an answer. One the provider sent inside a 2xx answer (an `error` object or event, MiniMax's
  `base_resp`, a finish reason that says the answer was cut off) raises `LLMAnswerError` with the status it stands for;
  an answer with no usable choice or a stream frame cut off on the way raises `LLMResponseError`. Both read as the
  provider's fault (overloaded, repeated) in `errors.classify_error`, never as a model that wrote bad output.
- Imports stay light: no provider SDK is loaded.
- A repeated request is answered from `answer_cache` for an hour, never with another request's answer: the key is the
  whole request on the wire, so another endpoint, credential, header, model or parameter asks the provider again, and
  only an answer that finished normally and carried something is kept (a failure, a truncated or filtered answer, an
  empty reply, a stream the consumer abandoned or the connection cut, and an upload are never stored). The cache is on
  by default; `MYRM_LLM_ANSWER_CACHE=0` switches it off, which is how the test suites start.
