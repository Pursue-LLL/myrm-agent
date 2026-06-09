# api/skill_optimization/

## 架构概述

技能质量优化 HTTP 层：Shadow A/B、版本对比与批量优化任务。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Skill Optimization API | ✅ |
| `dependencies.py` | 模块 | Return OptimizationScheduler instance. | ✅ |
| `metrics_provider.py` | 模块 | Skill Metrics Provider - re-export from services layer. | ✅ |
| `router.py` | 路由 | Skill Optimization API Router | ✅ |
| `ws_batch_progress.py` | 模块 | WebSocket Batch Progress Streaming | ✅ |
