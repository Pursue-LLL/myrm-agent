# engine/

## Overview

FetchEngine 执行引擎子包：L1 HTTP / L2 Browser / L3 Stealth 分层抓取入口，
职责按文件拆分（主引擎 + 缓存 / 抓取 / 升级三组 mixin + 共享类型），
`__init__.py` 聚合导出对外符号（保持 `toolkits.web_fetch.engine` 模块语义兼容）。

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | 聚合导出 base 公开符号（FetchEngine、结果类型、extract_* fast-path）。 | ✅ |
| base.py | Core | FetchEngine — tiered fetcher pool entry (mixins: cache / fetch / escalation); WeChat URLs log fast-path vs browser degradation outcomes | ✅ |
| types.py | Core | CachedDocument, AccessStats, BackgroundTask, result aliases | ✅ |
| cache_mixin.py | Core | Cache, coalescing, SWR background revalidation mixin; fetch error normalisation: an `SSRFSecurityError` from any tier is a terminal block (logged, remembered as failed, `None`), never an unexpected error and never a reason to try another tier | ✅ |
| fetch_mixin.py | Core | L1/L2/L3 fetch, degradation, router feedback mixin. A file (PDF, Office, image) is routed to a file parser before the empty-shell check; one no parser reads ends the fetch (a browser cannot read it either) but is still offered to the L4 remote providers, while an error status degrades as before. Text (plain, markdown, csv, feeds) is returned as it is, skipping the HTML-only checks. The router learns only from real outcomes: a final miss (404, 304, an unreadable file) is not reported | ✅ |
| escalation_mixin.py | Core | L4 remote escalation + bilibili cookie loader mixin | ✅ |

## Key Dependencies

- `..fetchers` (L1/L2/L3 fetcher 实现)
- `..router` (AdaptiveRouter 自适应路由)
- `..escalation` (L4 远程抓取 hook)
- `..pipeline` (HTML → Markdown 内容管道)
- `..*_extractor` (YouTube / Bilibili / WeChat fast-path)
