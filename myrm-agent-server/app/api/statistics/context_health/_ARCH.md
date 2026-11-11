# api/statistics/context_health/

## 架构概述

会话上下文健康度统计域：聚合健康度计算、缓存与恢复端点。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持外部 import 稳定 | ✅ |
| `context_health.py` | 门面 | 39 行纯转导出：构建入口、4 个健康 DTO、`CacheHealth` / `RetentionObservationState`；实现在 [builder/](builder/_ARCH.md) | — |
| `context_health_cache.py` | 模块 | 健康度计算结果缓存（避免重复聚合开销） | ✅ |
| `builder/` | 子包 | 健康度构建层，按阶段拆 5 个模块（models / coercion / compaction / pruning / build）。见 [builder/_ARCH.md](builder/_ARCH.md) | — |
| `context_health_restore.py` | 模块 | 健康度快照/聚合数据恢复端点 | ✅ |
