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
| `vault_resolver.py` | SSOT | 路径解析 + legacy 迁移 | ✅ |
| `vault_export.py` | 核心 | Export-only #10：`build_wiki_export_zip()` concepts + index/log + manifest | ✅ |
| `vault_service.py` | 生命周期 | 启动迁移、共享 archiver（cache key: llm + agent_id + manager） | ✅ |
| `agent_scope.py` | 辅助 | chat_id → agent_id，供 ingest / archive 选 vault | ✅ |
| `wiki_archive_hook.py` | 钩子 | compaction persist 后 SessionNotes 后台归档（按 chat.agent_id 选 vault） | ✅ |
| `consolidation_bridge.py` | 钩子 | consolidation 完成后 insight → `publish_raw` + enqueue（上游 enable_wiki 门控） | ✅ |
| `structural_stats_cache.py` | 辅助 | `/wiki/stats` structural lint 120s TTL 缓存；compile/maintain/repair-types/import/apply/delete concept/delete folder/pending approve/delete raw + ingest tree-sync 成功后失效 | ✅ |
| `obsidian_adapter.py` | 适配器 | Obsidian Vault 导入：`prepare_obsidian_file()` 转换 frontmatter/inline tags/images；`adapt_obsidian_file()` 仅测试/legacy 直写；生产 import 经 `router` → harness `publish_raw` | ✅ |
| `ingest_events.py` | 核心 | Wiki ingest SSE event bus；scope refcount 单 poll；best-effort publish；queue/compile snapshot；**tree_sync_required** 信号（stale/compile 指纹变化 → FE REST 刷新树 badge + **structural lint cache invalidate**） | ✅ |
