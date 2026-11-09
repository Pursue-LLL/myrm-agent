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
| `client.py` | Core | `LLMTransport` facade: route -> wire `prepare` -> HTTP -> decoded answer, shaped once by `chat_shape` (chat completions and streams; the Responses wire is read by its adapter); keeps no answers, so every call reaches the provider; sync/async; a Bedrock request without an API key is built off the event loop (`ChatWire.aprepare`), because the credential chain may read files and call a token service | ✅ |
| `profile.py` | Config | `ProviderProfile` data table (default endpoint, credential variables `api_key_env`, endpoint variables `api_base_env`, Azure's `api_version_env`), `resolve_route` (the call's endpoint and key, else the provider's own variables, else the default endpoint), `first_env`, `normalize_base_url`, `speaks_openai_body`; providers without a wire raise `UnsupportedProviderError` | ✅ |
| `params.py` | Core | `split_params`: transport options (credential, `azure_ad_token`, timeout, proxy, headers, `extra_body`) versus body parameters; `merge_headers` | ✅ |
| `http.py` | Core | Shared `httpx` clients per event loop (proxy- and TLS-policy aware; `aclose_clients` closes them at shutdown, `retire_clients` only forgets them when the TLS policy changes in a running process, so a stream being read is not cut), the retry loop of a request that allows one (`PreparedRequest.retries`), the `RequestSigner` that signs every attempt and redirect hop once it is built (a signature covers the attempt's bytes, time and address), the redirect hops of a gateway (a 307/308 on the configured host is sent again with the same body, headers and credential; a hop is not a retry), `ProviderStream` that remembers the provider's own finish reason (`finish_reason_of` reads it off a chunk) | ✅ |
| `redirects.py` | Core | Which redirect is followed and how one that is not reads: `followed_url` accepts only a 307/308 to the host that was configured (any port, never from https to http, web schemes only), `MAX_REDIRECTS` (5) bounds a loop, `redirect_notice` words a refused redirect as where it pointed, without its credentials, query or fragment | ✅ |
| `retry.py` | Core | Retry policy of one request: 408/409/429/5xx answers and refused or dropped connections are retried twice (0.5 s doubling to 8 s with jitter, the provider's Retry-After or `retry-after-ms` honoured while it fits the 8 s ceiling, `x-should-retry` obeyed); a read or write timeout and a longer Retry-After are passed up at once; only for failures before the provider produced anything | ✅ |
| `errors.py` | Core | `LLMCallError` (the base of the three failures below: one type for "the model call failed", which the server maps to an AI error code); `LLMHTTPError` (status, parsed body, response; a redirect that was not followed reads as where it pointed, not as the page a proxy sent with it); `LLMAnswerError` (a failure the provider sent inside a 2xx answer, carrying the status it stands for: `error_status`, MiniMax's `BASE_RESP_STATUS`); `LLMResponseError` (a 2xx answer that is not usable: not JSON, a stream frame cut off, no choice; reported as the 502 a gateway would; deliberately not a `ValueError`, so a route's "invalid input" handler never takes a provider's answer for the caller's input); the attribute shape `errors.normalize` reads | ✅ |
| `stream_events.py` | Core | `iter_stream_events` / `aiter_stream_events`: a streamed body in any of its three framings (SSE, NDJSON, the binary AWS event stream with its CRC-32 checks) reduced to `(event, data)` pairs; an exception or error message of the event stream becomes an `exception:<type>` / `error:<code>` event; a corrupted or cut-off message fails the stream like a cut-off JSON frame | ✅ |
| `frames.py` | Core | `json_frame`: the JSON object one stream frame carries; text that does not open an object (keep-alive word, `[DONE]`, `[PING]`) is skipped, an object that does not parse raises `LLMResponseError` instead of dropping content; shared by every wire's decoder | ✅ |
| `chat_shape.py` | Core | The one pass that gives the adapter the shape it assumes: `shape_usage` (counts as ints, total filled), `FINISH_REASONS` (every provider's finish word onto OpenAI's, a tool call wins over `stop`), `shape_completion` (role, message, choices checked), `answered_without` (the failure of a 2xx answer that holds no message, raised by every wire for a body that is not its answer), `shape_chunk`, `ShapedDecoder` | ✅ |
| `openai_chat.py` | Core | OpenAI Chat Completions wire (also Azure and every OpenAI-compatible provider): request, parse and SSE decoder; Azure sends a resource key as `api-key` and a Microsoft Entra token (`azure_ad_token`) as the only credential, `Authorization: Bearer`, with the API version of the call, else `AZURE_API_VERSION`, else `2025-02-01-preview` (its Responses calls take `preview` on the versionless `/openai/v1` route); the answer is the provider's own except that a top-level cache-read count (DeepSeek `prompt_cache_hit_tokens`, gateway `cache_read_input_tokens`) is also reported as `prompt_tokens_details.cached_tokens`, and a failure sent inside it (an `error` object, MiniMax `base_resp`, a cut-off finish reason: `error`, DeepSeek `insufficient_system_resource`/`aborted`) raises `LLMAnswerError` | ✅ |
| `openai_responses.py` | Core | OpenAI Responses wire: routing and credential only, the adapter assembles the body | ✅ |
| `capabilities.py` | Core | What a model takes in a request: `claude_traits` (sampling parameters, adaptive thinking, `xhigh`/`max` effort, output ceiling), `keeps_temperature_without_reasoning`, and the Gemini generation checks (`gemini_from_3`, `gemini_thinks_by_level`: a version gate, not a name prefix); the catalog's flags first, the model name for ids the catalog does not list | ✅ |
| `anthropic_messages.py` | Core | Anthropic Messages wire request: content blocks, cache markers, tool-call history (id alphabet, placeholder tool), blank-text and prefill rules, sampling parameters per model generation, default `max_tokens`; credential headers (an API key as `x-api-key`; a subscription token `sk-ant-oat…` as a bearer with the `oauth-2025-04-20` beta flag merged into the caller's flags, never as `x-api-key`) | ✅ |
| `anthropic_thinking.py` | Core | `request_thinking`: the `thinking` block and `output_config.effort` of a request (adaptive thinking with clamped effort, or a token budget); off when the replayed tool calls lack their signed thinking block | ✅ |
| `anthropic_response.py` | Core | Anthropic answer and event decoding into the chat shape, with cache accounting folded into the prompt total; an `error` event raises `LLMAnswerError`; a response that filled the context window finishes as `length` | ✅ |
| `anthropic_schema.py` | Core | Structured-output schema reduction to the subset the Messages API accepts | ✅ |
| `gemini_generate.py` | Core | Gemini generateContent wire: request (thinking budget before Gemini 3, thinking level from it and on the `-latest` aliases; JSON output left out where the API refuses it beside function declarations), answer and SSE decoding | ✅ |
| `gemini_contents.py` | Core | Chat history as alternating user/model `contents`: Gemini 3 and later call ids and `thoughtSignature` (carried in the tool-call id), media a tool returned (inside the function response on Gemini 3+, beside it elsewhere), a model turn kept between a tool result and a user message | ✅ |
| `gemini_schema.py` | Core | Tool-schema reduction to the Gemini subset | ✅ |
| `bedrock_converse.py` | Core | Bedrock Converse wire request (`/model/{id}/converse` and `/converse-stream`; a bearer API key, else the request carries a SigV4 signer from `bedrock_sigv4`; region from the ARN, the AWS variables or the AWS profile): the caller's tools and tool choice sent as stated, thinking per model family (Claude block, Nova 2 `reasoningConfig`, gpt-oss effort; an opaque ARN is treated as Claude), `parallel_tool_calls` as `disable_parallel_tool_use` where the catalog lists it, `top_k` where the model takes one, placeholder tool for replayed tool calls, Nova grounding | ✅ |
| `bedrock_sigv4.py` | Core | AWS Signature Version 4 for Bedrock: `load_credentials` resolves the botocore credential chain (environment, shared files, SSO, web identity, container or instance role; one session per source of credentials: kept for good while botocore renews its credentials, replaced after five minutes otherwise so that a rewritten file or helper output is read again), `request_signer` signs the bytes of each attempt (host, content type, date and `x-amz-*` headers); botocore (extra `bedrock`) is imported only here and only when a request is signed | ✅ |
| `bedrock_content.py` | Core | Chat history as strictly alternating Converse turns (merged neighbours, repaired tool-call ids, images and documents as bytes, cache points) and the reversible tool-name escape | ✅ |
| `bedrock_structured.py` | Core | Structured output on Bedrock: native `outputConfig.textFormat` for the models the catalog lists, otherwise one synthetic `json_tool_call` tool whose call is the answer | ✅ |
| `bedrock_response.py` | Core | Converse answer and event-stream decoding into the chat shape (reasoning and signed thinking blocks, tool calls, cache counters folded into the prompt total, the synthetic tool's call returned as text); an exception event raises `LLMAnswerError` with the status it stands for | ✅ |
| `ollama_chat.py` | Core | Native Ollama `/api/chat` wire (tools, structured output, thinking) with NDJSON decoding | ✅ |
| `json_schema.py` | Core | `inline_refs`: local `$ref` inlining shared by the Anthropic and Gemini schema converters | ✅ |
| `service_routes.py` | Config | Endpoint (the call's, else the provider's own variable, else its default) and credential (the call's only) resolution for embedding, rerank and image providers; `SERVICE_PROFILES` for the ones that serve no chat | ✅ |
| `embeddings.py` | Core | OpenAI-compatible `/embeddings`, Cohere `/embed` and Gemini `:batchEmbedContents`; a custom `api_base` is a gateway that keeps the whole model id | ✅ |
| `rerank.py` | Core | `/rerank` for Cohere, Jina, Together, SiliconFlow, Voyage and compatible gateways; an endpoint that stops short of a version segment gets the provider's (`/v2` Cohere, `/v1` Jina and Voyage) | ✅ |
| `images.py` | Core | Image generation and editing: OpenAI-family (an Azure deployment takes its API version as chat and embeddings do), Gemini, Stability, MiniMax | ✅ |

## Key Dependencies

- `httpx` (HTTP, proxy and TLS behavior; `infra.tls_compat` supplies the trust store)
- `botocore` (extra `bedrock`: only to sign Bedrock requests with AWS credentials; a deployment that authenticates with a Bedrock API key never loads it)
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
- A redirect never carries the credential or the conversation to another host. The provider key travels in a header httpx
  passes to whatever host an answer names (it removes `Authorization` only), so only a 307/308 to the configured host is
  followed (the body and headers sent again, the Location replacing the address and its query), never from https to http, at
  most 5 times; a 301, 302 or 303 would turn the POST into a GET that cannot carry the call. Every other redirect fails with
  the address it named, to be set as the provider's base URL.
- The adapter above reads plain dicts in OpenAI's shapes, so every chat answer is shaped once at the facade, whatever the
  wire or the gateway sent: token counts that are ints (a usage a provider leaves out stays empty; the call is still counted),
  a finish reason from OpenAI's five, a role, a message in every choice. A consumer carries no defence of its own.
- A failure is never read as an answer. One the provider sent inside a 2xx answer (an `error` object or event, MiniMax's
  `base_resp`, a finish reason that says the answer was cut off) raises `LLMAnswerError` with the status it stands for;
  an answer that holds no message (no usable choice; on a native wire a JSON object without the wire's message, which is how
  another API's reply or a status object looks) or a stream frame cut off on the way raises `LLMResponseError`. Both read as the
  provider's fault (overloaded, repeated) in `errors.classify_error`, never as a model that wrote bad output.
- A credential travels the way its provider reads it, once: a vendor key header or a bearer token, never both for one credential. Azure sends a resource key as `api-key`, a Microsoft Entra token as the bearer alone; Anthropic sends `x-api-key`, a subscription token as a bearer with its beta flag; Bedrock sends a bearer API key or a signature. Options that steer the transport (`azure_ad_token`, `proxy`, `api_version`) are read by `split_params` and never reach the request body, and a proxy a call names is the one its HTTP client connects through (a model's `egress_proxy` included: `tests/toolkits/llms/adapters/test_egress_proxy.py`). Pinned for every provider by `test_golden_credentials.py` (recorded against the previous client library), `test_request_isolation.py` and the wire tests.
- Imports stay light: no provider SDK is loaded. botocore is imported when a Bedrock request is signed, and its credential lookup runs off the event loop (`tests/blocking_io/test_bedrock_credentials_off_loop.py`).
- The transport keeps no answers: every call reaches the provider, so a key the provider has since revoked, an endpoint
  that has gone away and the latency a settings probe measures are never hidden behind an earlier success. A caller that
  wants a recorded answer asks for one explicitly (`memo_run`, the embedding cache). Pinned for chat, Responses,
  embeddings and rerank by `tests/toolkits/llms/transport/test_transport_keeps_no_answers.py`.
