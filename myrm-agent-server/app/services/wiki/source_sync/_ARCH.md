# source_sync/

## 架构概述

Wiki 外部来源确定性同步：Gmail 标签 / Google Drive 文件夹 / RSS / Integration mirror → harness `publish_raw` → 可选 compile enqueue。零 LLM pull；Cron 经 `__wiki_source_sync__` router job 触发。配置与 sync state 按 agent scope 存 UserConfig。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 runner 与 schema | — |
| `agent_scope.py` | 辅助 | agent_id → UserConfig nested key SSOT | ✅ |
| `schemas.py` | 类型 | `WikiSourceSyncConfig`（Gmail/GDrive/RSS/mirror）/ state / run summary DTO | ✅ |
| `config_store.py` | 持久化 | UserConfig `wikiSourceSync` 按 agent 读写 + exists 探测 | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiSourceSyncState` 上次同步状态（按 agent） | ✅ |
| `html_body.py` | 辅助 | Gmail HTML → Markdown（`HTML2Markdown`，ignore_images） | ✅ |
| `content_convert.py` | 辅助 | 云盘文件 bytes → Markdown（docx/pdf/text） | ✅ |
| `publish_helpers.py` | 辅助 | 统一 `publish_raw(caller=settings)` + frontmatter | ✅ |
| `gmail.py` | 连接器 | Google OAuth + Gmail API → raw/gmail/ | ✅ |
| `gdrive.py` | 连接器 | Google OAuth + Drive API → raw/gdrive/ | ✅ |
| `rss.py` | 连接器 | RSS/Atom HTTP → raw/rss/ | ✅ |
| `integration_mirror.py` | 钩子 | IntegrationSyncResult.new_items → raw/integrations/ | ✅ |
| `read_it_later_hygiene.py` | 迁移 | 存量 agent-type read-it-later Cron → router `__wiki_source_sync__` | ✅ |
| `defaults.py` | 默认 | Google OAuth / Second Brain apply 默认开 Gmail read-later | ✅ |
| `runner.py` | 编排 | `run_wiki_source_sync` SSOT（Gmail/GDrive/RSS/mirror + scoped state + post-sync dedup scan when published > 0） | ✅ |

## 测试

- `tests/services/wiki/test_source_sync_{gmail,gmail_html,gdrive,rss,state,config,defaults,blueprint}.py`
- `tests/services/wiki/test_read_it_later_hygiene.py`
- `tests/services/onboarding/test_second_brain_wiki_gmail.py`

## 依赖

- `app/services/integrations/oauth_store` — Google 连接探测
- `app/services/agent/oauth_refresher` — Gmail / Drive token
- `app/services/wiki/vault_service` — archiver / compile enqueue
- `app/api/integrations/google_workspace_oauth.py` — OAuth 成功默认开 Gmail sync
- `app/services/onboarding/second_brain_preset` — preset Gmail 默认 + cron id remap
- `app/api/wiki/sources.py` — REST（agent_id query）+ manual sync + state
- `app/core/cron/adapters/wiki_router_job_runner.py` — Cron router 执行体（source sync + maintain）
