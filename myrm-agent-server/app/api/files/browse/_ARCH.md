# app/api/files/browse 子包架构

Workspace 浏览 API。按端点域分模块，共享一个 `APIRouter` 与路径安全 helper；`app.api.files.browse` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 先 import 端点模块注册路由，再导出 `router` | — |
| `common.py` | 辅助 | `router`、logger、`_MAX_*` / `_IGNORED_DIRS` / `_TEXT_EXTENSIONS` 常量、响应模型、`_is_within_boundary` / `_is_text_file` / `_content_disposition` | ✅ |
| `listing.py` | 核心 | `_scan_tree`、`/browse`（只看目录）、`/browse/files`（文件+目录+元数据） | ✅ |
| `content.py` | 核心 | `/browse/content`：预览/下载，含 workspace 与 chat_id 边界校验 | ✅ |
| `search.py` | 核心 | `/browse/search`：harness `filesystem_suggest` SSOT 的文件名模糊搜索 | ✅ |

## 依赖关系

- 上游：harness `path_security` / `core.security.path` / `filesystem_suggest`、`app.core.utils.errors`、`app.core.utils.response_utils`
- 下游：前端 WorkspaceDirPicker / WorkspaceFileBrowser
