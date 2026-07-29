# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault_resolver.py`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST：… **GET /stats** 含 `structural_issues` + `asset_index`；**GET /assets/{filename}**；Obsidian import 含图时 **后台** `schedule_wiki_asset_index`（不阻塞 HTTP）；compile/maintain 同步 index；`_invalidate_wiki_structural_stats_cache` 在 compile/maintain/repair-types/import/**apply/delete concept/delete folder/pending approve/delete raw** 成功后失效 TTL | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；`get_wiki_archiver_for_ingest_stream` scoped dependency | ✅ |
