# memory/operations/crud 模块架构

记忆 CRUD 域处理器。由 `crud_handlers.py` facade 统一 re-export，供 `app/api/memory/operations/crud.py` 路由绑定。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `_common.py` | 辅助 | `_record_memory_event`、`_SORT_KEYS` | ✅ |
| `list_write.py` | 核心 | 列表、创建、更新、删除、搜索、统计、评分 | ✅ |
| `trash.py` | 核心 | 回收站列表、恢复、永久删除 | ✅ |
| `import_archive.py` | 核心 | 导出（JSON + Markdown ZIP）、归档、导入、回滚；竞品 dry-run 四车道；`resolve_migration_source` 强制 adapter；`instruction_total_chars` / `providers_configured` / `token_economics` 对照 | ✅ |
| `preferences.py` | 核心 | 偏好摘要与 pin/forget 管理 | ✅ |
