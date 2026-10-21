# api/statistics/context_health/

## 架构概述

会话上下文健康度统计域：由 `app/api/statistics/context_health*.py` 平铺模块拆分而来，聚合健康度计算、缓存与恢复端点。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持外部 import 稳定 | ✅ |
| `context_health.py` | 模块 | 会话上下文健康度聚合与统计端点 | ✅ |
| `context_health_cache.py` | 模块 | 健康度计算结果缓存（避免重复聚合开销） | ✅ |
| `context_health_restore.py` | 模块 | 健康度快照/聚合数据恢复端点 | ✅ |
