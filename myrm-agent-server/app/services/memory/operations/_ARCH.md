# services/memory/operations 模块架构

记忆 CRUD 业务处理器。HTTP 路由在 `app/api/memory/operations/crud.py` 薄绑定 handler 函数。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `crud_handlers.py` | 门面 | 从 `crud/` 子模块 re-export 全部 handler，供路由绑定 | ✅ |
| `crud/_common.py` | 辅助 | `_record_memory_event`、`_SORT_KEYS` 共享工具 | ✅ |
| `crud/list_write.py` | 核心 | 列表、创建、更新、纠正、删除、搜索、统计、评分、状态变更 | ✅ |
| `crud/trash.py` | 核心 | 回收站列表、恢复、永久删除 | ✅ |
| `crud/import_archive.py` | 核心 | 导出、归档、导入 dry-run/confirm、回滚预演与执行 | ✅ |
| `crud/preferences.py` | 核心 | 偏好摘要、偏好列表、pin/forget/unpin/unforget | ✅ |

## 依赖关系

- `app/schemas/memory/crud.py` — CRUD 请求/响应 Schema
- `app/schemas/memory/archive.py` — 归档/导入 Schema
- `app/services/memory/archive.py` — 归档服务
- `app/services/memory/import_sessions.py` — 导入会话服务
