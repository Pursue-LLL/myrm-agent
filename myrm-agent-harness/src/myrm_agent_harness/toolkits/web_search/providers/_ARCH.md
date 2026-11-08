# providers/

## Overview
Search provider adapters, orchestration, and priority-ordered failover chain.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports WebSearcher, SearchServiceConfig, LiteLLMSearch, search_provider_chain | ✅ |
| web_searcher.py | Core | Multi-provider search orchestrator with cache, coalescing, retry, and Document output; fills provider defaults the caller left unset (SearxNG language/categories/safesearch; Exa `contents.highlights`); maps the query's `site:` operators and the agent's `time_range` into the parameters of its own provider (`resolve_site_operators`, `resolve_time_range`); stamps each result with the provider that served it before the result enters the cache; the search cache key carries the factory's `credential_scope_digest` of the credential the request is billed and answered under; `SearchServiceConfig.provider_names` lists the providers a request through a config can reach (chain hops, else its own service), and an all-empty search names the `time_range` as a possible cause only when one of them maps the requested `time_range` | ✅ |
| search_service_factory.py | Core | Builds the concrete search client (native or LiteLLM, direct or gateway-routed) from a provider config, rejects missing credentials up front, and is the sole owner of the credential identity: `describe_credential_scope` reports the scope the routing decision implies (gateway token endpoint plus the direct key a routed request can fall back to) and `credential_scope_digest` is the single digest the result cache and the quota cooldown both address | ✅ |
| litellm_search.py | Core | LiteLLM search adapter for provider-agnostic API calls | ✅ |
| volcengine_doubao_search.py | Core | Volcengine Search Infinity native adapter | ✅ |
| bilibili_search.py | Core | Bilibili search fast-path via public API, taken only when every query is scoped to Bilibili videos by `site:` operators (`is_bilibili_video_query`: every included domain is `bilibili.com` or its `/video` section) and no `time_range` is set; the keyword it sends carries no `site:` operators; only entries that carry a video id become results (a live room has none), and HTML entities in a title or description are restored to text | ✅ |
| chain.py | Core | Priority-ordered provider chain runner: any failed hop or empty result list advances to the next provider within a wall-clock budget (all providers empty ends as an empty answer, not an error), passes the query and the agent's `time_range` to every hop unmapped so each hop's searcher maps the `site:` operators and the time range for its own provider, and every hop but the last yields after half of the remaining budget so a hung provider cannot starve the rest; quota and rate-limit failures cool the hop down under `quota_tracker_key` (provider slug plus the unguessable fingerprint of the credential the hop is billed under) whose depleted and rate-limited states both expire, so one exhausted account never benches a sibling key or a replacement key on the same slug | ✅ |

## Dependencies

- `web_search.core.common`, `web_search.core.error_handling`, `web_search.core.exceptions`
- `web_search.providers.search_service_factory` (credential identity of a hop: scope and digest)
- `web_search.coalescing` (result cache and in-flight coalescing of provider calls)
- `web_search.processing`
