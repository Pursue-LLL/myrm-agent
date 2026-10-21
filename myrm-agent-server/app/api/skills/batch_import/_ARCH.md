# api/skills/batch_import/

## 架构概述

技能批量导入（GUI-First 技能迁移）接口域：由 `app/api/skills/batch_import*.py` 平铺模块拆分而来，聚合批量导入的声明、执行、辅助与 schema。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持外部 import 稳定 | ✅ |
| `batch_import.py` | 模块 | 批量导入声明与状态接口（创建导入任务、查询进度） | ✅ |
| `batch_import_execute.py` | 模块 | 批量导入执行入口（串行/并行导入技能） | ✅ |
| `batch_import_helpers.py` | 模块 | 导入辅助逻辑（校验、重名处理、回滚支持） | ✅ |
| `batch_import_schemas.py` | 模块 | 导入请求/响应 Pydantic schema 与校验 | ✅ |
