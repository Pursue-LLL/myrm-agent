# memory/operations/crud 模块架构

记忆 CRUD 域处理器。由父目录 `crud_handlers.py` 门面统一 re-export（见 `operations/_ARCH.md`），供 `app/api/memory/operations/crud.py` 路由绑定。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `_common.py` | 辅助 | `_record_memory_event`、`_SORT_KEYS` | ✅ |
| `list_write.py` | 核心 | 列表、创建、更新、纠正、删除、搜索、统计、评分、状态变更 | ✅ |
| `item_mutations.py` | 核心 | 单条记忆更新/删除的唯一实现（用户保护语义：显式请求时锁定程序性规则/固定语义情景记忆，编辑程序性规则内容默认锁定；语义/情景软删除；异常映射 404/400）；记忆中心与学习时间线共用 | ✅ |
| `trash.py` | 核心 | 回收站列表、恢复、永久删除 | ✅ |
| `import_archive.py` | 门面 | re-export 导出/导入/回滚相态模块的全部 handler 与 token 基线常量，供 `crud_handlers.py` 与 token 经济测试保持单一导入点 | ✅ |
| `import_flows/` | 子模块 | 导入/导出/回滚相态实现（门面 `import_archive.py` 在本目录，路由只经门面引用）；见 [`import_flows/_ARCH.md`](import_flows/_ARCH.md) | ✅ |
| `preferences.py` | 核心 | 偏好摘要、偏好列表、pin/forget/unpin/unforget | ✅ |
