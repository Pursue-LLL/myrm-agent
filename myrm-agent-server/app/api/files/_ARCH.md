# api/files/

## 架构概述

文件上传、下载与 artifact 分享 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Files management API module | ✅ |
| `evicted.py` | 模块 | UECD evicted-file read API (`GET /evicted` paginated line-range); harness `read_evicted_line_range`; default `limit=500`; path traversal checks; missing file → HTTP 404 + `{"expired": true}` | ✅ |
| `artifact_api.py` | 模块 | List/retrieve/verify artifacts；`GET /files/artifacts` 支持可选 `limit`、`project_id` 与 `assessment_import_candidate` 查询参数（候选控量 + 项目相关候选过滤 + 评估导入资格语义探测：内容可解析性 + ledger 已导入检查，返回 `assessment_import_candidate.{status,reason}`，status 含 `importable/not_importable/already_imported/unknown`）；exposes `publications[]` per artifact；`POST /download-bundle` packages multiple artifacts into a single ZIP archive | ✅ |
| `artifact_share_api.py` | 模块 | Lets GUI users share html/pdf/document artifacts without publication deploy；支持活跃链接列表（`GET /shares`，为无密码链接按需重建 share_path 返回）、手动撤销（`DELETE /shares/{record_id}`，幂等 204/404，撤销写入审计日志）与撤销后公开入口 404（revoked_at 前置校验 + 拒绝重新 materialize），登记走 `services.artifacts.share_registry`；create/list 响应携带 `share_url`（基于 public-ingress SSOT 的绝对链接，托管/隧道部署可达，无 ingress 时降级为 `None` 由前端按 origin 组装） | ✅ |
| `artifact_share_public.py` | 模块 | 免认证公开入口（`/public/artifact-share/{token}`）三路由：入口/尾斜杠索引/静态资源；多文件 bundle 307 尾斜杠跳转；密码保护走 HMAC unlock cookie；CSP/nosniff/DENY 安全头（仅 HTML）；所有文件统一 `X-Robots-Tag: noindex, nofollow` + `Cache-Control: no-store`（防搜索引擎收录 + 撤销后即时生效）；撤销检查在认证前（已撤销链接包括密码链接直接 404，不展示密码框）；限流 30/60 | ✅ |
| `browse.py` | 模块 | Workspace browse API; `chat_id` 分支经 `effective_workspace` SSOT；`/browse/search` uses harness `filesystem_suggest`；`/browse/content` 文本内联 1MB 截断 + 二进制 FileResponse 全量流式（MIME + Range）；`FileEntry.is_text` 权威判定 + Content-Disposition RFC 5987 转义 | ✅ |
| `browse_watch.py` | 模块 | POST/DELETE `/browse/watch` — refcounted vault watch → `WORKSPACE_FILE_CHANGED` SSE. | ✅ |
| `hosting_api.py` | 模块 | Multi-target artifact publish, hosting targets CRUD, publications | ✅ |
| `document_extract.py` | 模块 | Document content extraction API. | ✅ |
| `local_actions.py` | 模块 | Local-only file reveal/open endpoints（依赖 `reveal_utils`） | ✅ |
| `pdf_extract.py` | 模块 | PDF content extraction API endpoint | ✅ |
| `revert.py` | 模块 | File revert & review API — exposes `revertible`/`skip_reason` on changes; hydrate/cleanup via `revert_hydrate`; Agent notify via `revert_agent_notify`. | ✅ |
| `router.py` | 路由 | Files API router | ✅ |
| `storage.py` | 模块 | 文件管理 API | ✅ |
| `suggest.py` | 模块 | `@` reference suggestion API — workspace via `effective_workspace` SSOT; uploaded/generated/wiki via harness + services. | ✅ |
| `upload.py` | 模块 | 文件上传 API | ✅ |
| `vault_api.py` | 模块 | Retrieve the raw binary/text content of a vault object. | ✅ |
| `vault_proxy.py` | 模块 | Vault secure artifact proxy router. | ✅ |
| `workspace_ops.py` | 模块 | Workspace file write operations API. | ✅ |
| `organize.py` | 模块 | Workspace organize HITL API — apply/rollback（含 `jobStatus`）/ latest-job | ✅ |
