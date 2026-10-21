# services/memory/archive/restore/

## 架构概述

记忆归档恢复域：把归档的记忆快照恢复回会话记忆空间，支持规划（planner）、执行（executor）、回滚（rollback）与通用工具。由 `app/services/memory/archive/` 拆分而来。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出恢复能力 | ✅ |
| `archive_restore.py` | 模块 | 归档恢复入口：任务编排与状态跟踪 | ✅ |
| `archive_restore_common.py` | 模块 | 恢复通用工具（分页、校验、错误码） | ✅ |
| `archive_restore_executor.py` | 模块 | 恢复执行器：将归档数据写回记忆存储 | ✅ |
| `archive_restore_planner.py` | 模块 | 恢复规划器：解析归档清单，产出恢复计划 | ✅ |
| `archive_restore_rollback.py` | 模块 | 恢复回滚：失败时还原记忆空间至恢复前状态 | ✅ |
