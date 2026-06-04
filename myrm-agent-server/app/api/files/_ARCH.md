# api/files 模块架构


---

## 架构概述

文件管理接口。通过 FilesService + StorageProvider 统一存储，支持 Local（本地）和 Sandbox（S3）两种模式。提供文件上传、存储管理、PDF 提取、Office 文档提取、工作区文件写操作（上传/新建目录/重命名/移动/删除/在线编辑保存）、本地文件操作（文件管理器定位、默认应用打开）和 GUI @ 结构化引用建议功能。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `router.py` | ✅ 入口 | 子路由注册 |
| `upload.py` | ✅ 核心 | 文件上传（通过 FilesService + StorageProvider），包含大图上传时的自动降采样压缩 (Downsampling) |
| `storage.py` | ✅ 核心 | 用户文件存储管理（列表、下载、删除） |
| `pdf_extract.py` | ✅ 核心 | PDF 提取 HTTP 端点（鉴权/限流）；解析委托 `services/files/content_extraction` |
| `document_extract.py` | ✅ 核心 | Office 提取 HTTP 端点；解析委托 `services/files/content_extraction` |
| `revert.py` | ✅ 核心 | 文件回退 + Review Diff API — 撤销 AI 文件编辑（消息级/文件级），Diff 内容获取（original vs current，供 Multi-Pane Review 面板使用） |
| `browse.py` | ✅ 核心 | 目录浏览与搜索 API — `/browse`、`/browse/files`、`/browse/content`（`workspace` 与/或 `chat_id` 定界；`chat_id` 可走 ChatService JIT 绑定沙箱根路径；相对 `path` 在根下解析）、`/browse/search`；含边界校验与敏感路径过滤 |
| `suggest.py` | ✅ 核心 | GUI @ 结构化引用建议 API — `/suggest`。按 `chat_id` 解析当前 workspace，聚合 workspace、uploaded、generated、special 引用，返回无绝对路径的 DTO |
| `workspace_ops.py` | ✅ 核心 | 工作区文件写操作 API — `/browse/upload`（文件上传到工作区目录，含 rate limit）、`/browse/mkdir`（新建目录）、`/browse/rename`（重命名）、`/browse/move`（移动）、`/browse/delete`（删除）、`/browse/content`（PUT，在线编辑保存）。6 层安全栈：边界校验 · 危险路径拦截 · 敏感文件守卫 · 文件名合法性 · 删除保护 · 上传限制。与 browse.py 职责分离（读写分离） |
| `local_actions.py` | ✅ 核心 | 本地文件操作 API — `/files/{file_id}/reveal`（文件管理器定位）、`/files/{file_id}/open`（默认应用打开）。仅本地部署模式可用，含三重安全校验（模式/路径/存在性），跨平台（macOS/Windows/Linux） | ✅ |
| `artifact_api.py` | ✅ 核心 | 工件 CRUD — 列表/单品 GET（含 `deployment_*`、`deployment_version_id`、`latest_version_id`）、版本历史、哈希校验 |
| `deploy_api.py` | ✅ 核心 | 一键部署 + `GET .../deploy/preflight`、sandbox `asset_root` 打包、限流、WS 状态 |
| `artifact_share_api.py` | ✅ 核心 | `POST .../share-preview` 签名只读链；`public_router` 免鉴权 inline 查看 |

---

## 依赖关系

- `app/services/files/content_extraction.py`：PDF/Office 解析（Kanban 与 HTTP 共用）
- `app/services/`：文件业务逻辑
- `app/services/deploy/`：`deploy_packager.py`（Vault 文件收集）、`VercelClient`（Vercel API v13）
