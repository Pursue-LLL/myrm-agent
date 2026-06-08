# api/files/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Files management API module | ✅ |
| `artifact_api.py` | 模块 | Provides REST endpoints for listing, retrieving, verifying artifacts; exposes deployment state and version staleness fields. """ | ✅ |
| `artifact_share_api.py` | 模块 | Lets GUI users share html/pdf/document artifacts without Vercel deploy. """ | ✅ |
| `browse.py` | 模块 | Workspace browse API. Provides read-only directory/file listing and content retrieval. Used by the frontend WorkspaceDirPicker (dirs only) and WorkspaceFileBrow | ✅ |
| `deploy_api.py` | 模块 | Provides one-click artifact deployment to Vercel and encrypted credential storage. """ | ✅ |
| `document_extract.py` | 模块 | Document content extraction API. Converts .docx/.xlsx/.xls/.pptx/.ppt to Markdown via Harness parsers. """ | ✅ |
| `local_actions.py` | 模块 | Local-only file action endpoints. Enables desktop-class UX for artifact files reveal in Finder/Explorer and open with default app. Security: restricted to local | ✅ |
| `pdf_extract.py` | 模块 | PDF content extraction API endpoint | ✅ |
| `revert.py` | 模块 | File revert & review API — undo AI file edits and review diffs. | ✅ |
| `router.py` | 路由 | Files API router | ✅ |
| `storage.py` | 模块 | 文件管理 API | ✅ |
| `suggest.py` | 模块 | File reference suggestion API. Resolves the current chat workspace and returns workspace, uploaded, generated and special references without exposing absolute p | ✅ |
| `upload.py` | 模块 | 文件上传 API | ✅ |
| `vault_api.py` | 模块 | Retrieve the raw binary/text content of a vault object. | ✅ |
| `vault_proxy.py` | 模块 | Vault secure artifact proxy router. | ✅ |
| `workspace_ops.py` | 模块 | Workspace file write operations API. | ✅ |
