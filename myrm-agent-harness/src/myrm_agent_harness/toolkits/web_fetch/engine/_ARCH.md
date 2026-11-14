# engine/

## Overview

FetchEngine 执行引擎子包：L1 HTTP / L2 Browser / L3 Stealth 分层抓取入口，
职责按文件拆分（主引擎 + 批量 / 缓存 / 抓取 / 升级四组 mixin + 共享类型），
`__init__.py` 聚合导出对外符号（保持 `toolkits.web_fetch.engine` 模块语义兼容）。

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | 聚合导出 base 公开符号（FetchEngine、结果类型）。 | ✅ |
| base.py | Core | FetchEngine — tiered fetcher pool entry (mixins: batch / cache / fetch / escalation). `crawl` owns the guards (SSRF, allowlist), coalescing, cache and fail-cache bookkeeping around one `_fetch_from_network` call; owns the fetches batch calls stopped waiting for until they end and cancels them on shutdown | ✅ |
| types.py | Core | CachedDocument, AccessStats, BackgroundTask, result aliases, the in-flight fetch future type and its `NO_SHARED_RESULT` marker | ✅ |
| cache_mixin.py | Core | Cache, coalescing, SWR background revalidation mixin. The revalidation workers start with the first stale hit that queues a refresh, not with the engine or its first crawl: an engine that never serves a stale entry (the one a local-mode tool call builds and drops) holds no task, so nothing is left pending for asyncio to report when it is collected. The coalescing wait is shielded (cancelling or timing out one waiter never cancels the future the others share); a leader cancelled mid-fetch resolves its future to `NO_SHARED_RESULT`, so its waiters come round again and one of them takes the fetch over instead of waiting out the coalescing timeout. Fetch error normalisation: an `SSRFSecurityError` from any tier is a terminal block (logged, remembered as failed, `None`), never an unexpected error and never a reason to try another tier | ✅ |
| fetch_mixin.py | Core | Network fetch, L1/L2/L3 degradation, tier-breaker feedback mixin. `_fetch_from_network` runs a URL's platform fast-path first (YouTube transcript, Bilibili subtitle, WeChat article, X post) and the tier ladder when it misses or the URL has none; each stage has its own crawl timeout (a URL whose fast-path misses can take twice the cap), and an error or timeout in the fast-path ends the crawl without the ladder. WeChat and X log which path served the URL. A file (PDF, Office, image) is routed to a file parser before the empty-shell check; one no parser reads ends the fetch (a browser cannot read it either) but is still offered to the L4 remote providers, while an error status degrades as before. Text (plain, markdown, csv, feeds) is returned as it is, skipping the HTML-only checks. The tier breaker learns only from real outcomes: a final miss (404, 304, an unreadable file) is not reported; a failed attempt also feeds the domain failure history behind the stale site-experience hint | ✅ |
| escalation_mixin.py | Core | L4 remote escalation + bilibili cookie loader mixin | ✅ |
| batch_mixin.py | Core | Batch crawling (`crawl_many`) and cache warm-up (`prefetch`, `prefetch_with_retry`) mixin. `crawl_many` judges every URL by how long its own fetch has run (a URL queued behind the concurrency cap is not penalised): with no page in hand yet it is awaited until its crawl timeout plus a 3 s unwind grace; once any page is in hand it is awaited 25 s. A URL the call stops waiting for is reported as failed, but its fetch keeps running under the engine's own crawl timeout (held in `_detached_fetches`), so callers coalesced on it and the page and failure caches are unaffected; a call holding a page never ends up empty and a hung URL cannot outlast the tool timeout. Fetches are cancelled only when their call is torn down or the engine shuts down, and never a second time once the crawl timeout has cancelled them (`Task.cancelling()`), which would cut their browser-page cleanup short | ✅ |

## Key Dependencies

- `..fetchers` (L1/L2/L3 fetcher 实现)
- `..router` (TierBreaker 按域名选起始层级、域名学习数据 DomainMetrics)
- `..escalation` (L4 远程抓取 hook)
- `..pipeline` (HTML → Markdown 内容管道)
- `..*_extractor` (YouTube / Bilibili / WeChat / X fast-path)
