# api/files/

## 架构概述

文件上传、下载与 artifact 分享 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Files management API module | ✅ |
| `artifact_api.py` | 模块 | List/retrieve/verify artifacts; exposes `publications[]` per artifact | ✅ |
| `artifact_share_api.py` | 模块 | Lets GUI users share html/pdf/document artifacts without publication deploy | ✅ |
| `browse.py` | 模块 | Workspace browse API; `/browse/search` uses harness `filesystem_suggest`. | ✅ |
| `hosting_api.py` | 模块 | Multi-target artifact publish, hosting targets CRUD, publications | ✅ |
| `document_extract.py` | 模块 | Document content extraction API. | ✅ |
| `local_actions.py` | 模块 | Local-only file action endpoints. | ✅ |
| `pdf_extract.py` | 模块 | PDF content extraction API endpoint | ✅ |
| `revert.py` | 模块 | File revert & review API — exposes `revertible`/`skip_reason` on changes; hydrate/cleanup via `app/services/files/revert_hydrate.py`. | ✅ |
| `router.py` | 路由 | Files API router | ✅ |
| `storage.py` | 模块 | 文件管理 API | ✅ |
| `suggest.py` | 模块 | `@` reference suggestion API — workspace/uploaded/generated/wiki via harness `filesystem_suggest` + `WikiStructure`. | ✅ |
| `upload.py` | 模块 | 文件上传 API | ✅ |
| `vault_api.py` | 模块 | Retrieve the raw binary/text content of a vault object. | ✅ |
| `vault_proxy.py` | 模块 | Vault secure artifact proxy router. | ✅ |
| `workspace_ops.py` | 模块 | Workspace file write operations API. | ✅ |
