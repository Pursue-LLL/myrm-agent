# services/wiki 模块架构


## 架构概述

Wiki 知识库服务层：Memory→Wiki 归档、vault 路径 SSOT、启动迁移、compaction 后 SessionNotes 后台归档。REST `/api/wiki/stats` 返回 **cognitive map** 字段与 **`structural_issues`**（deterministic broken markdown/wikilink links — path + frontmatter title alias — invalid frontmatter types，raw-backed provenance gaps，120s TTL 缓存 via `structural_stats_cache.py`）。

## Vault SSOT

- **Canonical path**: `{harness_dir}/wiki/agents/{agent_id}/` — `vault.resolve_wiki_vault_path(agent_id)`
- **Shared read-only**: `{harness_dir}/wiki/shared/{context_id}/` — via `resolve_shared_wiki_vault_path()`
- **Legacy paths** (one-time migration): `{state_dir}/wiki`, `~/.myrm/users/sandbox/wiki`
- **Startup**: `vault.init_wiki_vault_at_startup()` from FastAPI lifespan
- **Shared archiver**: `vault.get_wiki_archiver()` — API、SessionNotes 归档、Deep Research vault、consolidation digest 共用

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `memory_to_wiki.py` | 核心 | 记忆转 Wiki（`publish_raw` + enqueue compile；security_blocked 跳过）；支持 harness SessionNotes 与 legacy JSON；`query_wiki` 返回结构化 QueryResult | ✅ |
| `vault/` | 域 | vault 生命周期 + 路径 SSOT + export + git hooks；见 [`vault/_ARCH.md`](vault/_ARCH.md) | ✅ |
| `maintain/` | 域 | maintain 编排 + schemas + state 持久化；见 [`maintain/_ARCH.md`](maintain/_ARCH.md) | ✅ |
| `obsidian/` | 域 | Obsidian 导入适配 + export presets；见 [`obsidian/_ARCH.md`](obsidian/_ARCH.md) | ✅ |
| `agent_scope.py` | 辅助 | chat_id → agent_id（vault 选择）+ agent_id → UserConfig scope key 规范化（state/config store 共用） | ✅ |
| `_userconfig_scoped.py` | 辅助 | 共享 UserConfig scoped JSON 持久化（load/save/merge，agent-scoped） | ✅ |
| `wiki_archive_hook.py` | 钩子 | compaction persist 后 SessionNotes 后台归档（按 chat.agent_id 选 vault） | ✅ |
| `consolidation_bridge.py` | 钩子 | consolidation 完成后 insight → `publish_raw` + enqueue（上游 enable_wiki 门控） | ✅ |
| `structural_stats_cache.py` | 辅助 | `/wiki/stats` structural lint 120s TTL 缓存；`_after_wiki_vault_mutation` SSOT 在 compile/maintain/repair-types/repair-publication/move/import/apply/delete concept/delete folder/pending approve/delete raw 等变更后失效 | ✅ |
| `knowledge_query_service.py` | SSOT | `execute_wiki_knowledge_query` — Settings POST /query 与 Chat Wiki Knowledge Lane 共用零 LLM 检索 + citations | ✅ |
| `chat_compound_service.py` | SSOT | `stage_chat_compound_from_message` — POST /compound DB hydrate Q&A + trust → harness pending；reject inactive/incognito assistant messages | ✅ |
| `health_report_service.py` | SSOT | GET /wiki/health-report structural scan + merge vault full snapshot drift + `count_open_actions`；maintain 写入/读取 `reports/last-health.json` | ✅ |
| `dedup_runner.py` | SSOT | `schedule_wiki_dedup_scan` (202 background) / `run_wiki_dedup_scan_job` (cron blocking) / `apply_wiki_dedup_disposition` / `wiki_dedup_checklist_ready` — POST /dedup/* 与 Cron `__wiki_dedup__` 共用；compile 进行中 skip scan | ✅ |
| `clip/` | 核心 | Browser extension clip — `form.py` 8MB cap · `runner.py` async jobs → harness `publish_clip_ingress` · post-write ingest SSE；见 [`clip/_ARCH.md`](clip/_ARCH.md) | ✅ |
| `wiki_query_intent.py` | 辅助 | Chat Wiki Knowledge Lane 确定性准入闸门（`should_use_wiki_knowledge_lane`） | ✅ |
| `asset_index_service.py` | 核心 | Obsidian wiki/assets vision caption 索引；`build_vision_fallback_engine_from_providers` 有序视觉链；import 后 `schedule_wiki_asset_index` 后台运行并在完成后 publish ingest snapshot；compile/maintain 同步 `run_wiki_asset_index` | ✅ |
| `ingest_events.py` | 核心 | Wiki ingest SSE event bus；scope refcount 单 poll；best-effort publish；queue/compile snapshot；snapshot stats 含 **`synthesis_pending_count`**；**tree_sync_required** / **stats_refresh_required** 信号 → FE REST 刷新；指纹并入本地可写 `concepts/` 编译页 stat（mtime_ns+size），Agent 编辑词条 → UI 自动刷新 | ✅ |
| `source_sync/` | 核心 | Gmail/GDrive/RSS 确定性 pull → `publish_raw` + compile enqueue + post-sync dedup scan；Integration mirror；Cron router；闭包：HTML2Markdown、Cron hygiene、sync state、Second Brain Gmail 默认 | ✅ |
