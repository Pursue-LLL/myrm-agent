# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault_resolver.py`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST：… claims 响应含 `resource_uri` / `superseded_from_uri`；**POST /query** 经 `knowledge_query_service.execute_wiki_knowledge_query` SSOT；**POST /vault/reveal** + **POST /vault/open-obsidian**（#22）；**GET /portability/export**；`_after_wiki_vault_mutation` SSOT（**13 处** · #23 git + stats cache） | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；`get_wiki_archiver_for_ingest_stream` scoped dependency | ✅ |
| `sources.py` | 路由 | **GET/PUT /sources/config**（`agent_id` query · `google_drive_authorized` · scoped sync state）· **POST /sources/sync** — Gmail/GDrive/RSS 配置与手动同步 | ✅ |
