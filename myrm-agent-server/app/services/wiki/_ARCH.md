# services/wiki 模块架构


## 架构概述

Wiki 知识库服务层：Memory→Wiki 归档、vault 路径 SSOT、启动迁移、compaction 后 SessionNotes 后台归档。REST `/api/wiki/stats` 返回 **cognitive map** 字段与 **`structural_issues`**（deterministic broken markdown/wikilink links — path + frontmatter title alias — and invalid frontmatter types，120s TTL 缓存 via `structural_stats_cache.py`）。

## Vault SSOT

- **Canonical path**: `{harness_dir}/wiki/agents/{agent_id}/` — `vault_resolver.resolve_wiki_vault_path(agent_id)`
- **Shared read-only**: `{harness_dir}/wiki/shared/{context_id}/` — via `resolve_shared_wiki_vault_path()`
- **Legacy paths** (one-time migration): `{state_dir}/wiki`, `~/.myrm/users/sandbox/wiki`
- **Startup**: `vault_service.init_wiki_vault_at_startup()` from FastAPI lifespan
- **Shared archiver**: `vault_service.get_wiki_archiver()` — API、SessionNotes 归档、Deep Research vault、consolidation digest 共用

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `memory_to_wiki.py` | 核心 | 记忆转 Wiki（`publish_raw` + enqueue compile；security_blocked 跳过）；支持 harness SessionNotes 与 legacy JSON；`query_wiki` 返回结构化 QueryResult | ✅ |
| `vault_resolver.py` | SSOT | 路径解析 + legacy 迁移 + `seed_agent_vault_from_default`（Second Brain preset 默认 vault→新 agent + SCHEMA.md seed） | ✅ |
| `vault_export.py` | 核心 | Obsidian-ready full vault ZIP（harness archive + server graph preset） | ✅ |
| `obsidian_export.py` | 适配器 | `.obsidian/graph.json` + README for Settings download | ✅ |
| `vault_git_snapshot.py` | 钩子 | `after_wiki_vault_mutation` SSOT + async git schedule (#23) | ✅ |
| `vault_git_status.py` | 辅助 | `/wiki/stats` vault git visibility fields (Local/Tauri) | ✅ |
| `vault_service.py` | 生命周期 | 启动迁移、共享 archiver（cache key: llm + agent_id + manager） | ✅ |
| `agent_scope.py` | 辅助 | chat_id → agent_id，供 ingest / archive 选 vault | ✅ |
| `wiki_archive_hook.py` | 钩子 | compaction persist 后 SessionNotes 后台归档（按 chat.agent_id 选 vault） | ✅ |
| `consolidation_bridge.py` | 钩子 | consolidation 完成后 insight → `publish_raw` + enqueue（上游 enable_wiki 门控） | ✅ |
| `structural_stats_cache.py` | 辅助 | `/wiki/stats` structural lint 120s TTL 缓存；`_after_wiki_vault_mutation` SSOT 在 compile/maintain/repair-types/repair-publication/move/import/apply/delete concept/delete folder/pending approve/delete raw 等变更后失效 | ✅ |
| `knowledge_query_service.py` | SSOT | `execute_wiki_knowledge_query` — Settings POST /query 与 Chat Wiki Knowledge Lane 共用零 LLM 检索 + citations | ✅ |
| `maintain_runner.py` | SSOT | `run_wiki_maintain_job` — POST /maintain?mode= 与 Cron `__wiki_maintain__` 共用；compile 进行中 skip | ✅ |
| `maintain_state_store.py` | 持久化 | UserConfig `wikiMaintainState` 上次维护 observability（按 agent） | ✅ |
| `wiki_query_intent.py` | 辅助 | Chat Wiki Knowledge Lane 确定性准入闸门（`should_use_wiki_knowledge_lane`） | ✅ |
| `asset_index_service.py` | 核心 | Obsidian wiki/assets vision caption 索引；import 后 `schedule_wiki_asset_index` 后台运行并在完成后 publish ingest snapshot；compile/maintain 同步 `run_wiki_asset_index` | ✅ |
| `obsidian_adapter.py` | 适配器 | Obsidian Vault 导入：`prepare_obsidian_file()` 转换 frontmatter/inline tags/images；`adapt_obsidian_file()` 仅测试/legacy 直写；生产 import 经 `router` → harness `publish_raw` | ✅ |
| `ingest_events.py` | 核心 | Wiki ingest SSE event bus；scope refcount 单 poll；best-effort publish；queue/compile snapshot；snapshot stats 含 **`synthesis_pending_count`**；**tree_sync_required** / **stats_refresh_required** 信号 → FE REST 刷新 | ✅ |
| `source_sync/` | 核心 | Gmail/GDrive/RSS 确定性 pull → `publish_raw` + compile enqueue；Integration mirror；Cron router；闭包：HTML2Markdown、Cron hygiene、sync state、Second Brain Gmail 默认 | ✅ |
