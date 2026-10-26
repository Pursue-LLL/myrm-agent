# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST 主 router；**POST /query**（提问先过风控闸门，被拦返回 400 `risk_held`，不检索、不调模型）· **POST /compile**（202：把需要编译的原文入队并唤醒导入同用的后台 worker，立即返回 `pending` 与 `compile_run`，进度走 ingest 流；去重待审返回 409）· **POST /compound** · **POST /daily-review**（复盘原文 verbatim 存证 raw/DailyReview + 编译入队，同日同题幂等 skip，安全扫描 422）· **POST /templates/seed**（四张标准模板幂等种子，`force` 显式覆盖）· **GET /pending**（HITL 待审草稿分页列表，`limit≤200`/`offset`，stats 恒精确）· **GET /concepts/{name:path}/links**（双向链接查询：出链 `{name, exists}`，入链另带 `context_snippet`/`heading`；每个方向有条数上限（harness `MAX_CONCEPT_LINKS`），被截断的方向由 `outlinks_has_more`/`backlinks_has_more` 标出）· **GET /concepts/{name:path}**（`get_concept` 返回 `source_chat`/`source_message` 溯源字段）· **POST /reindex-vectors**（published L2 + sidecar + optional asset vector rebuild + errors[]）· **POST /meeting-notes/transcribe**（批量会议音频→纪要）· **POST/GET /meeting-notes/live/{session_id}[/ingest|/finalize]**（会中实时滚动纪要；`ingest` 必填 `line_id`（幂等去重）、拒绝空白行与非有限 `timestamp`，全部以 422 快速失败） | ✅ |
| `maintain_routes.py` | 路由 | **POST /maintain?mode=**（202：启动后台维护，已有进行中的一轮则返回它的状态；compile 进行中返回 409）· **POST /maintain/cancel**（幂等：让进行中的一轮在模型调用之间或等待某次调用时停下，已写入的保留；返回当前状态）· **GET /maintain/status**（`state` idle/running/succeeded/cancelled/failed、`phase`、`done`/`total`、`cancel_requested`、`result`、`error_code`；失败只给错误码，不给异常原文） | ✅ |
| `routes/clip.py` | 路由 | **POST /clip** (202 multipart) · **GET /clip/{job_id}** · **GET/PUT /wikiignore** | ✅ |
| `routes/ima.py` | 路由 | **/sources/ima/\*** 腾讯 ima 知识库导入：凭证、选库、同步控制、状态与条目报告、仅编译 ima 文档；详见 [`routes/_ARCH.md`](routes/_ARCH.md) | ✅ |
| `archiver_dependency.py` | 依赖 | `get_scoped_wiki_archiver`：所有 wiki 路由共用的请求级 archiver 依赖，绑定用户配置的模型与所请求的 vault（编译、问答、变更类端点用它）；只读写 vault 文件的端点改用 `app.services.wiki.vault.get_wiki_structure`，不会在没有模型时构造出占住编译 worker 槽位的 archiver | ✅ |
| `ingest_stream.py` | 路由 | **GET /ingest/stream** SSE；经 `get_scoped_wiki_archiver` 取 archiver | ✅ |
| `governance_routes.py` | 路由 | **/governance/\*** 知识治理工作台：overview · extend · archive · undo · revive（经 vault 索引，archiver 来自 `get_scoped_wiki_archiver`） | ✅ |
| `sources.py` | 路由 | **GET/PUT /sources/config**（`agent_id` query · `google_drive_authorized` · scoped sync state）· **POST /sources/sync** — Feishu/Gmail/GDrive/RSS/Zotero/mirror 配置与手动同步 | ✅ |
