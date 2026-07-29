# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault_resolver.py`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST：… **POST /wiki/maintain** 返回 `raw_security_removed` + paths；import 经 harness `publish_raw`（skip/supersede + `conflict_paths` + `security_blocked_paths` / `security_redacted_paths`）；**DELETE /wiki/raw/{path}**（`forget_evidence` + reason）；**GET /concepts** 含 `editor_sections` + `content_hash` | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；`get_wiki_archiver_for_ingest_stream` scoped dependency | ✅ |
