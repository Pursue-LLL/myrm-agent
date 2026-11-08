# web_search/

## Overview
Web search toolkit entry point. Aggregates and re-exports search tools, result types,
and the intent-aware search parameter optimizer.

## Submodule Index

| Submodule | Role | Description |
|-----------|------|-------------|
| [core/](core/_ARCH.md) | Core | Shared types, exceptions, error handling |
| [providers/](providers/_ARCH.md) | Core | Provider adapters, WebSearcher orchestrator, failover chain |
| [processing/](processing/_ARCH.md) | Core | Result dedup/sort, intent optimizer, citation resolver, explicit params |
| [coalescing/](coalescing/_ARCH.md) | Core | Single-flight search API deduplication and LRU cache keys scoped to the credential identity the factory owns |
| [probe/](probe/_ARCH.md) | Core | SearXNG local discovery probes and region presets |

## Package Root Files

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Toolkit entry point; lazy re-exports WebSearchTools, RestSearch, SearchServiceConfig | ✅ |
| engine.py | Core | WebSearchTools wrapper: parallel per-question search, one shared merge (round-robin, dedup, domain diversity), first `top_k` returned | ✅ |
| web_search_agent_tools.py | Core | LangChain `web_search_tool` factory; `fetch_and_extract_available` tells it whether the agent's `web_fetch_tool` offers `fetch_and_extract` | ✅ |
| _web_search_tool_description.py | Core | LLM-visible tool description SSOT (EN/ZH); recommends `fetch_and_extract` only when the agent's `web_fetch_tool` offers it | ✅ |

## Package Root Files (facade only)

Root `.py` files are limited to orchestration facade and LangChain adapter; shared types live under `core/`.

## Key Dependencies

- `utils`
- `[retrieval]` extra — `web_search_agent_tools.py` lazily imports `toolkits/retriever/sufficiency` only when the sufficiency guard is enabled

## Intent-Aware Search Flow

```
User query → LLM Query Rewriting → questions: list[str]
  → engine.fast_search_with_questions(questions, explicit_params?)
    → processing._explicit_params.normalize_explicit_params(explicit_params, provider)
    → processing.intent_optimizer.detect_search_intent(query) per query
    → processing.intent_optimizer.resolve_search_params(intent, provider) per query
    → Fusion: explicit_params > intent_override > config.extra_params
    → IF provider=tavily AND query contains site: → map to search_domain_filter
    → Per-question documents (one list per question, from the first source that applies):
      IF all queries = PLATFORM_BILIBILI:
         providers.bilibili_search.search_bilibili() per query
         (on failure → fallback: site:bilibili.com via generic search)
      ELIF all queries = CODE:
         providers.github_code_search.search_github_code() per query
         (on failure → fallback: generic search)
      ELSE:
         providers.WebSearcher.search(query, extra_params_override=fused_override)
         (when provider_chain set → providers.chain search_provider_chain failover)
         coalescing.await_coalesced_search deduplicates concurrent identical searches
         (same provider, credential, query, limit and params)
         (TTL cache skipped when the provider payload has no usable URL results)
    → processing.combine_search_results_unified()    (same merge for every source)
         round-robin across questions + URL/content dedup: no question is crowded out
    → processing.apply_domain_diversity_sort()
    → _drop_blocked_hostname_docs()
    → first top_k of the merged order (search-engine ranking is the relevance signal)
    → processing.citation_resolver.enrich_sources_with_resolved_urls()
```

## Three-Priority Parameter Fusion

Search parameters are merged with highest-priority-wins:
1. **Agent explicit_params** (highest) — from tool call (time_range)
2. **Intent optimizer auto-detection** — keyword-based regex classification
3. **config.extra_params** (lowest) — user/admin search service defaults

`normalize_explicit_params()` in `processing/_explicit_params.py` converts unified Agent params to
provider-specific formats. When intent confidence is below threshold (0.6), search behaves as GENERAL intent.
