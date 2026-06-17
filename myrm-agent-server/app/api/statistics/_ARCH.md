# api/statistics/

## 架构概述

会话分析、上下文健康与 rate limit 统计 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Statistics package entrypoint. | ✅ |
| `agent_usage.py` | 模块 | Per-Agent usage analytics — per-agent token/cost breakdown with sparkline trends. | ✅ |
| `context_health.py` | 模块 | Statistics context-health layer. | ✅ |
| `context_health_cache.py` | 模块 | Statistics API cache-health layer. | ✅ |
| `context_health_restore.py` | 模块 | Statistics API restore-health normalization layer. | ✅ |
| `daily_journal.py` | 模块 | Daily journal API. | ✅ |
| `growth_dashboard.py` | 模块 | Growth Dashboard API — aggregated view of agent growth metrics + cost/savings summary. | ✅ |
| `rate_limits.py` | 模块 | API endpoints for fetching real-time rate limit statistics | ✅ |
| `router.py` | 路由 | Base statistics routes: usage, daily, sessions, activity, tool-stability, badges. | ✅ |
| `session_analytics.py` | 模块 | 会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。 | ✅ |
| `usage_aggregation.py` | 模块 | Coerce SQLAlchemy Row / tuple results into aggregate_usage inputs. | ✅ |
