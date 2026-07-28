# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault_resolver.py`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST：query/compile/maintain/repair-types/ingest/import/concepts/queue/pending/graph/stats；pending approve 422 阻断无效 frontmatter `type`；`/query` 返回 answer + related_articles + source_snippets；`?agent_id=` + ingest 从 artifact.chat_id 解析；`/stats` 含 `cognitive_index_ready`/`cognitive_log_entries`/`cognitive_hot_updated_at`；compile/maintain/pending/repair-types/import(no auto-compile) 触发 cognitive map refresh | ✅ |
