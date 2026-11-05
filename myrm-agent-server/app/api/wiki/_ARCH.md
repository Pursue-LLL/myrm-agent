# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | 组合根：按原路径顺序挂载 `routes/` 下的领域路由（query/dedup/stats/tree/mutations/queue/insights/imports/vault/portability/url_import/video_import/meeting）与独立子路由（clip/ima/maintain/sources/governance/layers/obsidian-binding），并注册 ingest stream；端点细节见各子模块与 [`routes/_ARCH.md`](routes/_ARCH.md) | ✅ |
| `maintain_routes.py` | 路由 | **POST /maintain?mode=**（202：启动后台维护，已有进行中的一轮则返回它的状态；compile 进行中返回 409）· **POST /maintain/cancel**（幂等：让进行中的一轮在模型调用之间或等待某次调用时停下，已写入的保留；返回当前状态）· **GET /maintain/status**（`state` idle/running/succeeded/cancelled/failed、`phase`、`done`/`total`、`cancel_requested`、`result`、`error_code`；失败只给错误码，不给异常原文） | ✅ |
| `routes/clip.py` | 路由 | **POST /clip** (202 multipart) · **GET /clip/{job_id}** · **GET/PUT /wikiignore** | ✅ |
| `routes/ima.py` | 路由 | **/sources/ima/\*** 腾讯 ima 知识库导入：凭证、选库、同步控制、状态与条目报告、仅编译 ima 文档；详见 [`routes/_ARCH.md`](routes/_ARCH.md) | ✅ |
| `archiver_dependency.py` | 依赖 | `get_scoped_wiki_archiver`：所有 wiki 路由共用的请求级 archiver 依赖，绑定用户配置的模型与所请求的 vault（编译、问答、变更类端点用它）；只读写 vault 文件的端点改用 `app.services.wiki.vault.get_wiki_structure`，不会在没有模型时构造出占住编译 worker 槽位的 archiver | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；经 `get_scoped_wiki_archiver` 取 archiver | ✅ |
| `governance_routes.py` | 路由 | **/governance/\*** 知识治理工作台：overview · extend · archive · undo · revive（经 vault 索引，archiver 来自 `get_scoped_wiki_archiver`） | ✅ |
| `sources.py` | 路由 | **GET/PUT /sources/config**（`agent_id` query · `google_drive_authorized` · scoped sync state）· **POST /sources/sync** — Feishu/Gmail/GDrive/RSS/Zotero/mirror 配置与手动同步 | ✅ |
