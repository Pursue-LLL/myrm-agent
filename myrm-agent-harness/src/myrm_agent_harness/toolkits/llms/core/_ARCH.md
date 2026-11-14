# core/

## Overview
LLM core: LLM classes, manager, and credential pool.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | LLM core: LLM classes, manager, and credential pool. | — |
| credential_pool.py | Core | Framework-level credential scheduling and rotation. Selectable strategies (round_robin/fill_first/random/least_used) with exponential backoff + jitter, Retry-After support, success acknowledgment, and observability stats. | ✅ |
| deepseek_reasoning.py | Core | DeepSeek reasoning_effort & thinking protocol parameter mapping. Maps reasoning effort levels ('low', 'high', 'max') and handles thinking on/off ('enabled'/'disabled') for DeepSeek models to guarantee compatibility and tool-call reasoning_content safety. DeepSeek models behind another provider's OpenAI-shaped endpoint (OpenCode Go, SiliconFlow, NVIDIA, custom; recognised by bare model id) follow the same effort mapping and explicit off switch, but a request that selects nothing is left untouched and a level adds no `thinking` field. | ✅ |
| key_pool_llm.py | Core | Framework-level LLM wrapper. Transparent key rotation on RATE_LIMIT/AUTH/BILLING errors with Retry-After extraction, success reporting, and challenge circuit breaker (immediately halts pool rotation and raises EgressChallengeBlockedError on WAF/anti-bot blocks). Sits below ManagedLLM in the call chain. | ✅ |
| llm.py | Core | LLM core. Factory over the in-house model transport providing a unified multi-model invocation interface. Integrates reasoning_timeout floor, thinking headroom adjustment, local endpoint stall-detection relaxation, and native web_search auto-detection. Reasoning-effort normalization runs in a fixed order: DeepSeek mapping, OpenAI remap, omission of an 'off' that no rule translated (OpenAI-shaped bodies only), OpenRouter `reasoning.effort` rewrite, then output headroom. OpenRouter's own disable switch is not guessed: models that always reason refuse it. Extra model kwargs are also forwarded to OpenAI-compatible providers as `extra_body` entries (a caller `extra_body` wins and is copied, never mutated); the output cap, `extra_body` itself and the factory-only `supports_reasoning` switch are never forwarded that way, because the transport lays `extra_body` over the typed request fields and would put the pre-headroom cap on the wire. First-party Anthropic Messages calls skip the `extra_body` copies entirely (that API rejects the field; the Anthropic wire maps `reasoning_effort` to `thinking` itself). | ✅ |
| manager.py | Core | LLM manager. Provides efficient strategy-aware LLM instance management with LRU caching for improved performance. `get_llm_from_config` 统一 temperature 与 reasoning_effort 语义：顶层字段优先覆盖 `model_kwargs`，与 agent builder 装配路径保持一致。 | ✅ |
| openai_reasoning.py | Core | OpenAI reasoning_effort parameter remap & normalization. Remaps non-standard reasoning effort levels ('minimal'→'low', 'xhigh'/'max'→'high') for OpenAI reasoning models (o1, o3, o4, GPT-5.6), strips unsupported 'off' values, and safely removes reasoning_effort for non-reasoning models (gpt-4o, gpt-4o-mini) to prevent API HTTP 400 Bad Request errors. An OpenAI model is recognised by the first-party endpoint, Azure, or a GPT/o-series bare model id; models other providers serve through the shared `openai/` route segment are not OpenAI models. | ✅ |
| openrouter_verbosity.py | Core | OpenRouter reasoning_effort → reasoning.effort parameter mapping. Rewrites top-level reasoning_effort into OpenRouter's extra_body.reasoning.effort format, so the effort reaches models like Claude 4.6+ instead of being rejected as an unknown top-level field. | ✅ |
| reasoning_profile.py | Core | Reasoning model single source of truth (SSOT) profile and intent contract. Unifies timeout floors, output token headroom budgets, and three-tier intent resolution (L1 explicit intent, L2 config toggle, L3 authoritative catalog fallback). `apply_thinking_headroom` raises a configured cap below the floor within the model's documented output ceiling; the raised value is what reaches the provider. `strip_untranslated_off_effort` omits an 'off' effort (top level and `extra_body`) that no provider rule translated, since OpenAI-shaped endpoints have no 'off' value. | ✅ |
| reasoning_route.py | Core | `ReasoningRoute` / `resolve_reasoning_route`: provider, bare lowercase model id, first-party endpoint flag and OpenAI-shaped-body flag of one call, from the same route facts the wire router uses. The leading segment of a model id names the wire protocol, not the model family, so reasoning-parameter rules read this instead of matching the route string. | ✅ |
| reasoning_timeout.py | Core | Reasoning model timeout floor detection facade. Delegates to reasoning_profile SSOT for unified timeout floors. | ✅ |
| thinking_headroom.py | Core | Thinking model max_tokens headroom adjustment facade. Delegates to reasoning_profile SSOT for token budget floors. | ✅ |

Wire protocol selection is configured via `LLMConfig.wire_protocol` / `TransportChatModel.wire_protocol` and implemented in `adapters/wire/` (see [adapters/wire/_ARCH.md](../adapters/wire/_ARCH.md)).

## Key Dependencies

- `utils`
