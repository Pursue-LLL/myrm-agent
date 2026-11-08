# processing/

## Overview
Search result post-processing, query identifier pinning, explicit constraint mapping, and citation resolution.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports result processors, explicit constraint mappers and identifier pinning | ✅ |
| search_results_processor.py | Core | Multi-query Round-Robin interleaving, two-layer dedup (URL comparison key, content hash; a document shows its winning result's own URL with percent-escaped non-ASCII characters restored), domain diversity sort, Document conversion | ✅ |
| citation_resolver.py | Core | SSRF-safe citation redirect resolution, tracking parameter stripping, and source normalization | ✅ |
| identifier_pinning.py | Core | Exact-phrase pinning of the CVE ids and DOIs that stand outside a double-quoted phrase in a query | ✅ |
| _explicit_params.py | Core | Agent explicit constraints to provider parameters: `time_range` per provider (SearXNG, Tavily, Volcengine Doubao) with a caveat when a provider cannot apply it exactly; the query's `site:` / `-site:` operators whose value is a host (optionally with a path) to Tavily's `search_domain_filter` / `exclude_domains`, while every other provider keeps them in the query; `split_site_operators` is the one reading of that grammar, shared with the Bilibili fast-path | ✅ |

## Dependencies

- `web_search.core.common`, `web_search.core.exceptions`
- `core.security.http.secure_fetch` (SSRF-safe redirect resolution for `citation_resolver.py`)
