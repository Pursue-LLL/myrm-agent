# engine/

## Overview

FetchEngine 执行引擎子包：L1 HTTP / L2 Browser / L3 Stealth 分层抓取入口，
职责按文件拆分（主引擎 + 批量 / 缓存 / 抓取 / 升级四组 mixin + 共享类型），
`__init__.py` 聚合导出对外符号（保持 `toolkits.web_fetch.engine` 模块语义兼容）。

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | 聚合导出 base 公开符号（FetchEngine、结果类型、extract_* fast-path）。 | ✅ |
| base.py | Core | FetchEngine — tiered fetcher pool entry (mixins: batch / cache / fetch / escalation); WeChat URLs log fast-path vs browser degradation outcomes | ✅ |
| types.py | Core | CachedDocument, AccessStats, BackgroundTask, result aliases | ✅ |
| cache_mixin.py | Core | Cache, coalescing, SWR background revalidation mixin; fetch error normalisation: an `SSRFSecurityError` from any tier is a terminal block (logged, remembered as failed, `None`), never an unexpected error and never a reason to try another tier | ✅ |
| fetch_mixin.py | Core | L1/L2/L3 fetch, degradation, tier-breaker feedback mixin. A file (PDF, Office, image) is routed to a file parser before the empty-shell check; one no parser reads ends the fetch (a browser cannot read it either) but is still offered to the L4 remote providers, while an error status degrades as before. Text (plain, markdown, csv, feeds) is returned as it is, skipping the HTML-only checks. The tier breaker learns only from real outcomes: a final miss (404, 304, an unreadable file) is not reported; a failed attempt also feeds the domain failure history behind the stale site-experience hint | ✅ |
| escalation_mixin.py | Core | L4 remote escalation + bilibili cookie loader mixin | ✅ |
| batch_mixin.py | Core | Batch crawling (`crawl_many`) and cache warm-up (`prefetch`, `prefetch_with_retry`) mixin | ✅ |

## Key Dependencies

- `..fetchers` (L1/L2/L3 fetcher 实现)
- `..router` (TierBreaker 按域名选起始层级、域名学习数据 DomainMetrics)
- `..escalation` (L4 远程抓取 hook)
- `..pipeline` (HTML → Markdown 内容管道)
- `..*_extractor` (YouTube / Bilibili / WeChat fast-path)
