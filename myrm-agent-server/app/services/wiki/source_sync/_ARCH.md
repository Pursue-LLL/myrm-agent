# source_sync/

## 架构概述

Wiki 外部来源确定性同步：Gmail 标签 / RSS / Integration mirror → harness `publish_raw` → 可选 compile enqueue。零 LLM pull；Cron 经 `__wiki_source_sync__` router job 触发。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 runner 与 schema | — |
| `schemas.py` | 类型 | `WikiSourceSyncConfig` / `WikiSourceSyncState` / run summary DTO | — |
| `config_store.py` | 持久化 | UserConfig `wikiSourceSync` 读写 | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiSourceSyncState` 上次同步状态 | ✅ |
| `html_body.py` | 辅助 | Gmail HTML → Markdown（与 email channel 同源 `HTML2Markdown`） | ✅ |
| `publish_helpers.py` | 辅助 | 统一 `publish_raw(caller=settings)` + frontmatter | ✅ |
| `gmail.py` | 连接器 | Google OAuth + Gmail API → raw/gmail/ | ✅ |
| `rss.py` | 连接器 | RSS/Atom HTTP → raw/rss/ | ✅ |
| `integration_mirror.py` | 钩子 | IntegrationSyncResult.new_items → raw/integrations/ | ✅ |
| `read_it_later_hygiene.py` | 迁移 | 存量 agent-type read-it-later Cron → router `__wiki_source_sync__` | ✅ |
| `runner.py` | 编排 | `run_wiki_source_sync` SSOT + 同步后写 state | ✅ |

## 依赖

- `app/services/integrations/oauth_store` — Google 连接探测
- `app/services/agent/oauth_refresher` — Gmail token
- `app/services/wiki/vault_service` — archiver / compile enqueue
- `app/api/wiki/sources.py` — REST + manual sync
- `app/core/cron/adapters/wiki_source_sync_runner.py` — Cron router 执行体
