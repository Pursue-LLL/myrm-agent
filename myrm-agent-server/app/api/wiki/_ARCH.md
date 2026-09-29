# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST 主 router；**POST /compound** · **GET /concepts/{name:path}/links**（双向链接与局部图谱查询）· **GET /concepts/{name:path}**（`get_concept` 返回 `source_chat`/`source_message` 溯源字段）· **POST /reindex-vectors**（published L2 + sidecar + optional asset vector rebuild + errors[]）· **POST /meeting-notes/transcribe**（批量会议音频→纪要）· **POST/GET /meeting-notes/live/{session_id}[/ingest|/finalize]**（会中实时滚动纪要；`ingest` 必填 `line_id`（幂等去重）、拒绝空白行与非有限 `timestamp`，全部以 422 快速失败） | ✅ |
| `routes/clip.py` | 路由 | **POST /clip** (202 multipart) · **GET /clip/{job_id}** · **GET/PUT /wikiignore** | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；`get_wiki_archiver_for_ingest_stream` scoped dependency | ✅ |
| `sources.py` | 路由 | **GET/PUT /sources/config**（`agent_id` query · `google_drive_authorized` · scoped sync state）· **POST /sources/sync** — Feishu/Gmail/GDrive/RSS/Zotero/mirror 配置与手动同步 | ✅ |
