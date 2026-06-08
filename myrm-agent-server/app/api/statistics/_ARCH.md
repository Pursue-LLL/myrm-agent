# api/statistics/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Statistics package entrypoint. Keeps submodule imports lightweight and composes routers only when the main API router asks for them. """ | ✅ |
| `context_health.py` | 模块 | Statistics context-health layer. Converts low-level usage, pruning, archive restore, adaptive backoff, and prompt-cache metrics into stable API health signals.  | ✅ |
| `context_health_cache.py` | 模块 | Statistics API cache-health layer. Owns provider/model sample selection so the context-health aggregate can stay focused on composition. """ | ✅ |
| `context_health_restore.py` | 模块 | Statistics API restore-health normalization layer. Converts raw task metrics into small, typed payloads before the main context-health aggregate is serialized.  | ✅ |
| `daily_journal.py` | 模块 | Daily journal API. Provides a consolidated day-level view of all agent activity across sessions, approvals, cron runs, kanban events, and tool calls. """ | ✅ |
| `growth_dashboard.py` | 模块 | Growth Dashboard API — aggregated view of agent growth metrics. | ✅ |
| `rate_limits.py` | 模块 | API endpoints for fetching real-time rate limit statistics. """ | ✅ |
| `router.py` | 路由 | Parse ISO date string to timezone-aware datetime. | ✅ |
| `session_analytics.py` | 模块 | 会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。 """ | ✅ |
| `usage_aggregation.py` | 模块 | Coerce SQLAlchemy Row / tuple results into aggregate_usage inputs. | ✅ |
