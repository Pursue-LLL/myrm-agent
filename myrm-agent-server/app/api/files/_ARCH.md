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
| `pdf_extract.py` | ✅ 核心 | PDF 内容提取（文本 + 图片） |
| `document_extract.py` | ✅ 核心 | Office 文档提取（.docx/.xlsx/.xls/.pptx/.ppt → Markdown），使用 Harness file_parsers |
| `revert.py` | ✅ 核心 | 文件回退 + Review Diff API — 撤销 AI 文件编辑（消息级/文件级），Diff 内容获取（original vs current，供 Multi-Pane Review 面板使用） |
| `browse.py` | ✅ 核心 | 目录浏览与搜索 API — `/browse`、`/browse/files`、`/browse/content`（`workspace` 与/或 `chat_id` 定界；`chat_id` 可走 ChatService JIT 绑定沙箱根路径；相对 `path` 在根下解析）、`/browse/search`；含边界校验与敏感路径过滤 |
| `suggest.py` | ✅ 核心 | GUI @ 结构化引用建议 API — `/suggest`。按 `chat_id` 解析当前 workspace，聚合 workspace、uploaded、generated、special 引用，返回无绝对路径的 DTO |
| `workspace_ops.py` | ✅ 核心 | 工作区文件写操作 API — `/browse/upload`（文件上传到工作区目录，含 rate limit）、`/browse/mkdir`（新建目录）、`/browse/rename`（重命名）、`/browse/move`（移动）、`/browse/delete`（删除）、`/browse/content`（PUT，在线编辑保存）。6 层安全栈：边界校验 · 危险路径拦截 · 敏感文件守卫 · 文件名合法性 · 删除保护 · 上传限制。与 browse.py 职责分离（读写分离） |
| `local_actions.py` | ✅ 核心 | 本地文件操作 API — `/files/{file_id}/reveal`（文件管理器定位）、`/files/{file_id}/open`（默认应用打开）。仅本地部署模式可用，含三重安全校验（模式/路径/存在性），跨平台（macOS/Windows/Linux） | ✅ |
| `artifact_api.py` | ✅ 核心 | 工件 CRUD — 列表/单品 GET（含 `deployment_*`）、版本历史、哈希校验 |
| `deploy_api.py` | ✅ 核心 | 工件一键部署 — POST deploy、WS 状态流（服务端读 DB token）、Vercel 凭据加密存储 |

---

## 依赖关系

- `app/services/`：文件业务逻辑
- `app/services/deploy/`：`VercelClient` 部署实现
