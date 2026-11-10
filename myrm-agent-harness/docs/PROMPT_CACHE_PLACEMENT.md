# Prompt Cache Placement (SSOT)

Placement rules for **where dynamic context may appear** relative to the provider prefix cache. Implementation detail lives in [PROMPT_CACHE_PRACTICE.md](../src/myrm_agent_harness/agent/context_management/PROMPT_CACHE_PRACTICE.md).

## Provider serialize order

Most chat APIs materialize requests as:

```text
Tool definitions → System prompt → Messages (oldest → newest)
```

Prefix cache matches from the start of that byte stream. Anything that changes **earlier** in the stream invalidates cache for everything after it.

## What stays in the frozen prefix

| Content | Placement | Rationale |
|---------|-----------|-----------|
| Tool schemas | Front (sorted by layer/name) | See `ToolLayer` / registry in PROMPT_CACHE_PRACTICE §2.1 |
| System prompt | System message, append-only | Do not inject time, memory, or tool results here |

## What must NOT be in the system prompt

| Dynamic content | Placement in Myrm harness |
|-----------------|---------------------------|
| Wall-clock / timezone | Trailing segment on **HumanMessage** (see PROMPT_CACHE_PRACTICE §2.2) |
| User memory block | A separate **SystemMessage** `<user_memory_context>` after the leading system messages (`memory_context_middleware.py`), rebuilt on every model call from the turn's memory context and never written back to the thread state; the system prompt text itself carries no memory |
| Knowledge-base snippets for this turn's question | Final **HumanMessage** tail inside an untrusted-data envelope via `proactive_pack_middleware.py`; the host retrieves them per turn and passes them in the run context, so the memory brief and the history before the final message stay byte-identical |
| Ephemeral session deltas (LWW) | Final **HumanMessage** tail inside `<ephemeral_session_deltas>`; includes a short `<precedence>` line so deltas override stable memory on conflict (`ephemeral_delta/tail_injector.py`) |
| Tool results | Message history only; never rewrite prior turns to “refresh” memory |
| User instructions / channel delivery | Human-side injection per PROMPT_CACHE_PRACTICE §2.4–2.5 |

## Metrics (measured vs layout)

Do **not** equate “stable layout” with “100% cache hit”. Observe provider usage:

| Field / surface | Source |
|-----------------|--------|
| `cache_read_input_tokens`, `cache_creation_input_tokens` | Provider usage on completion |
| `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens` | OTLP `chat` span attributes written by `ModelCall.finish` in `infra/tracing/gen_ai/model_call.py` |
| Session trace `prompt_cache_hit_ratio` | `myrm-agent-server` `session_trace_enrichment.py` (`total_cache_read_tokens / total_prompt_tokens`) |
| `TokenTracker` / `compute_prompt_cache_stats` | `utils/token_economics/tracker.py`, `cache_economics.py` |
| Ephemeral delta API | Layout only: delta count, system hash from preview inject, injection latency—**no** provider hit ratio |

## Product surfaces (SSOT)

| Surface | User | Cache hit rate |
|---------|------|----------------|
| Chat `ContextUsageIndicator` | All GUI users | **Yes** — `health.cache.cache_hit_rate` from provider usage |
| Session trace / OTLP | Ops, analytics | **Yes** — `prompt_cache_hit_ratio` / `cache_read_*` |
| Memory command center ephemeral metrics | Advanced / session overrides | **No** — layout & in-flight delta count only; do not show fake percentages |
| Memory command center **Two-layer studio** | Lab / API preview only (`NEXT_PUBLIC_MEMORY_LABS=1`) | **No** — cadence/dialectic experiments; its output is never injected into agent turns. |
| Settings → Runtime snapshot | Local / desktop ops | **N/A** — liveness & memory pressure (`GET /api/v1/ops/snapshot`); not cache hit rate |

## Product copy

User-facing text should describe **prefix stability** and **measured** hit ratios where data exists. Avoid absolute guarantees (“100% hit”, “guaranteed cache”).

## Related code index

- Explicit `cache_control` breakpoints: `toolkits/llms/core/llm.py`
- Roll-forward / preheat: `preheat.py`, `prompt_cache_roll_forward/`
- Break detection: `agent/context_management/infra/cache_break_detector.py`, `agent/context_management/infra/cache_metrics_collector.py`
