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
| `daily_wrap.py` | 模块 | Daily Wrap API — AI-generated daily activity summary with SQLite caching. | ✅ |
| `growth_dashboard.py` | 模块 | Growth Dashboard API — aggregated view of agent growth metrics, cost/savings summary, and per-skill usage efficiency trends. | ✅ |
| `rate_limits.py` | 模块 | API endpoints for fetching real-time rate limit statistics | ✅ |
| `router.py` | 路由 | Base statistics routes: usage, daily, sessions, activity, tool-stability, badges（含 activeGoals 计数）. | ✅ |
| `session_analytics.py` | 模块 | 会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。 | ✅ |
| `usage_aggregation.py` | 模块 | Coerce SQLAlchemy Row / tuple results into aggregate_usage inputs；聚合 token/cost/cache 指标并输出端到端 `streamTtft` 统计摘要（sampleCount/avg/p95，基于 `streamTtftMs` 样本，不依赖 usage 字段是否存在）。 | ✅ |
| `wiki_evidence.py` | 模块 | Wiki 证据链观测 API：写入 evidence_surface/snippet_open/snippet_close/query_submitted/dropped_report/quality_outcome_negative 事件（支持 `context_key` 口径隔离；`quality_outcome_negative` 当前由含 KB 证据回答的 Regenerate/Undo 触发），聚合输出 snippet expansion、deep verification、re-query、quick bounce、dwell 与 negative outcome 指标；内置 90 天 retention 周期清理；在 dropped/snippet/outcome 触发事件上评估治理告警，并通过系统通知+冷却去重（内存+DB）形成闭环。 | ✅ |
