# web_search/

## Overview
Web search toolkit entry point. Aggregates and re-exports search tools and result types,
and maps the constraints the agent states explicitly onto each provider.

Bug ledgers (local-only: git-ignored and excluded from the wheel): `web_search_<start>_<end>_BUGFIX_LOG.md` in this directory, one file per 7-day window.

## Submodule Index

| Submodule | Role | Description |
|-----------|------|-------------|
| [core/](core/_ARCH.md) | Core | Shared types, exceptions, error handling |
| [providers/](providers/_ARCH.md) | Core | Provider adapters, WebSearcher orchestrator, failover chain |
| [processing/](processing/_ARCH.md) | Core | Result dedup/sort, citation resolver, explicit constraints, identifier pinning |
| [coalescing/](coalescing/_ARCH.md) | Core | Single-flight search API deduplication and LRU cache keys scoped to the credential identity the factory owns |
| [probe/](probe/_ARCH.md) | Core | SearXNG local discovery probes and region presets |

## Package Root Files

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Toolkit entry point; lazy re-exports WebSearchTools, LiteLLMSearch, SearchServiceConfig | ✅ |
| engine.py | Core | WebSearchTools wrapper: parallel per-question search, one shared merge (round-robin, dedup, domain diversity), first `top_k` returned | ✅ |
| web_search_agent_tools.py | Core | LangChain `web_search_tool` factory; `fetch_and_extract_available` tells it whether the agent's `web_fetch_tool` offers `fetch_and_extract` | ✅ |
| _web_search_tool_description.py | Core | LLM-visible tool description SSOT (EN/ZH); recommends `fetch_and_extract` only when the agent's `web_fetch_tool` offers it | ✅ |

## Package Root Files (facade only)

Root `.py` files are limited to orchestration facade and LangChain adapter; shared types live under `core/`.

## Key Dependencies

- `utils`
- `[retrieval]` extra — `web_search_agent_tools.py` lazily imports `toolkits/retriever/sufficiency` only when the sufficiency guard is enabled

## Search Flow

```
User query → LLM Query Rewriting → questions: list[str]
  → engine.fast_search_with_questions(questions, time_range?)
    → processing.identifier_pinning.pin_structured_identifiers(question) per question
      (CVE ids and DOIs outside a double-quoted phrase are wrapped in double quotes; nothing else in the question changes)
    → Per-question documents (one list per question):
      IF every question is scoped to Bilibili videos by site: (providers.bilibili_search.is_bilibili_video_query) AND no time_range:
         providers.bilibili_search.search_bilibili() for every question at once
         (the API takes plain keywords: the query's site: operators are removed from the keyword first)
         (a question the API returns nothing for goes to the provider search below, as written; the others keep the API's documents)
         (when that provider search fails the answered questions stand; when the API answered none, its error surfaces)
      ELSE (a time_range is set, or not every question is scoped to Bilibili videos):
         (every question goes as written, including one scoped to Bilibili)
         providers.WebSearcher.multi_query_parallel_search(queries, time_range)
         (the provider that serves the request maps the query's site: operators
         (processing._explicit_params.resolve_site_operators) and the time_range (resolve_time_range) into its own
         parameters)
         (when provider_chain set → providers.chain search_provider_chain failover; each hop maps both for itself)
         coalescing.await_coalesced_search deduplicates concurrent identical searches
         (same provider, credential, query, limit and params)
         (TTL cache skipped when the provider payload has no usable URL results)
         (each result is stamped with the provider that served it before it enters the cache)
    → processing.combine_search_results_unified()    (same merge for every source)
         round-robin across questions (each takes turns) + URL/content dedup; the decay and the top_k cut below decide what survives
         (spelling variants of one URL fold into one document by a comparison key that is never shown; the document shows its
         winning result's own URL, with percent-escaped non-ASCII characters restored)
    → processing.apply_domain_diversity_sort()
    → _drop_blocked_hostname_docs()    (a leading www. does not change which entry matches a host)
    → first top_k of the merged order (search-engine ranking is the relevance signal)
    → utils.context_format.format_documents_with_metadata(index_for=source_indexer_var.get())
         (each unique URL gets one label `【n】`; inside a run n is the number the run's SourceTracker.index_for hands out
         for that source, so the card the stream issues later carries the same index, across calls and tools; without a
         bound run the labels count from 1; a document the token budget drops leaves its number unused)
    → sources_metadata: the engine tags each source with the provider that returned it (`search_provider`); the formatted context does not name providers
    → processing.citation_resolver.enrich_sources_with_resolved_urls()
    → web_search_tool: reads the tags for the `Time filter notice`, then returns the sources without them
```

## Explicit Constraints

Two things the agent states explicitly are applied beyond the query text: its `time_range` (`day` / `week` / `month` /
`year`, or `YYYY-MM-DD..YYYY-MM-DD`) and the `site:` / `-site:` operators of a question; nothing is inferred from the
query. Each provider hop maps them for itself, so a chain failover never forwards one provider's parameters to another.
Both win over `config.extra_params` and reach the result-cache key through the merged provider parameters.
`resolve_time_range()` in `processing/_explicit_params.py` maps the time range for the provider that serves each request:

| Provider | Parameters sent |
|----------|-----------------|
| `searxng` | `time_range` bucket; a date range becomes the smallest bucket covering its start (older than a year: no filter) |
| `tavily` | `time_range` bucket, or `start_date` / `end_date` for a range |
| `volcengine_doubao` | `TimeRange` (`OneDay` / `OneWeek` / `OneMonth` / `OneYear`, or the range string) |
| any other provider | nothing |

When a provider cannot apply the value exactly (a date range on SearXNG, a provider without time parameters, an
unparseable value) it receives the nearest bucket or nothing, and a caveat states the difference. `web_search_tool`
appends one `Time filter notice` line, after the untrusted-content block, naming the caveats of the providers that
served the results (results that name no provider: every configured provider); an all-empty search names `time_range`
as a possible cause only when a provider in `SearchServiceConfig.provider_names` maps the requested `time_range` (the
chain hops, else its own service; a hop skipped on cooldown still counts).

`resolve_site_operators()` in the same module maps the operators for the provider that serves each request:

| Provider | Handling |
|----------|----------|
| `tavily` | `site:` becomes `search_domain_filter` (LiteLLM `include_domains`) and `-site:` becomes `exclude_domains`; the operators leave the query text unless nothing else remains (a query of only operators keeps its text) |
| any other provider | no domain filter is mapped; the query is sent as written |

A `site:` value must be a host with an optional path (`gov.cn`, `.edu`, `*.edu`, `中国.cn`, `github.com/openai`) and an
ASCII top-level domain. Anything else after `site:` (`<domain>`, an IP, a port, a scheme, `gov.cn，site:edu.cn`) is no
domain filter and stays in the query.

`split_site_operators()` is the one reading of this grammar. `resolve_site_operators()` maps what it returns for Tavily;
the Bilibili fast-path sends the API a keyword without operators, and takes `site:` operators as scoping a query to
Bilibili videos only when every domain they include is `bilibili.com` or its `/video` section (`-site:bilibili.com`
excludes the site, a second domain widens the search beyond it, and the other sections such as `/read` hold what the
video API cannot return). A question that merely mentions Bilibili is no scope.
