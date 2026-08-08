# source_sync/

## 架构概述

Wiki 外部来源确定性同步：Gmail 标签 / Google Drive 文件夹 / RSS / Integration mirror → harness `publish_raw` → 可选 compile enqueue。零 LLM pull；Cron 经 `__wiki_source_sync__` router job 触发。配置与 sync state 按 agent scope 存 UserConfig。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包级文档；消费者直接 import runner / schemas / config_store / state_store | — |
| `schemas.py` | 类型 | `WikiSourceSyncConfig`（Feishu/Gmail/GDrive/RSS/mirror）/ state / run summary DTO | ✅ |
| `config_store.py` | 持久化 | UserConfig `wikiSourceSync` 按 agent 读写 + exists 探测 | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiSourceSyncState` 上次同步状态（按 agent） | ✅ |
| `content_convert.py` | 辅助 | 云盘文件 bytes → Markdown（sniff+docx embed→wiki/assets） | ✅ |
| `publish_helpers.py` | 辅助 | 统一 `publish_raw(caller=settings)` + frontmatter | ✅ |
| `feishu/` | 连接器 | Feishu 域 — 门面 + 渲染纯函数；见 [`feishu/_ARCH.md`](feishu/_ARCH.md) | ✅ |
| `gmail/` | 连接器 | Gmail 域 — 门面 + HTML 渲染；见 [`gmail/_ARCH.md`](gmail/_ARCH.md) | ✅ |
| `gdrive.py` | 连接器 | Google OAuth + Drive API → raw/gdrive/ | ✅ |
| `rss.py` | 连接器 | RSS/Atom HTTP → raw/rss/ | ✅ |
| `integration_mirror.py` | 钩子 | IntegrationSyncResult.new_items → raw/integrations/ | ✅ |
| `read_it_later_hygiene.py` | 迁移 | 存量 agent-type read-it-later Cron → router `__wiki_source_sync__` | ✅ |
| `defaults.py` | 默认 | Google OAuth / Second Brain apply 默认开 Gmail read-later | ✅ |
| `runner.py` | 编排 | `run_wiki_source_sync` SSOT（Feishu/Gmail/GDrive/RSS/mirror + scoped state + post-sync dedup scan when published > 0） | ✅ |

## 测试

- `tests/services/wiki/test_source_sync_{gmail,gmail_html,gdrive,rss,state,config,defaults,blueprint}.py`
- `tests/services/wiki/test_feishu_source_sync.py` — Feishu Docx blocks 全量渲染（标题/列表/嵌套列表缩进+独立计数/代码+围栏自适应/引用/待办/文件块/图片/行内样式+链接+URL解码/议程块/通用降级/@用户/@文档/日期提醒/公式/`$`转义）
- `tests/services/wiki/test_feishu_images.py` — 图片下载→wiki/assets 落盘 + 失败降级
- `tests/services/wiki/test_read_it_later_hygiene.py`
- `tests/services/onboarding/test_second_brain_wiki_gmail.py`

## 依赖

- `app/services/wiki/_userconfig_scoped` — 共享 UserConfig scoped JSON 持久化（config/state store 复用）
- `app/services/integrations/oauth_store` — Google 连接探测
- `app/services/agent/oauth_refresher` — Gmail / Drive token
- `app/services/wiki/vault` — archiver / compile enqueue
- `app/api/integrations/google_workspace_oauth.py` — OAuth 成功默认开 Gmail sync
- `app/services/onboarding/second_brain_preset` — preset Gmail 默认 + cron id remap
- `app/api/wiki/sources.py` — REST（agent_id query）+ manual sync + state
- `app/core/cron/adapters/wiki_router_job_runner.py` — Cron router 执行体（source sync + maintain）
