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
| `assessment_import.py` | 模块 | 评估导入观测 API：写入 `import_attempted/import_succeeded/import_failed/dropped_report` 事件（维度含 `surface`、`trigger`、`failure_reason`）；聚合导入成功率/失败率、recent-candidate 入口占比、失败原因分布；并提供 `value-summary`（优先按 `import_id`，兼容回退 `project_id + artifact_version_id` 关联导入台账与任务/里程碑状态，输出导入后任务完成率、里程碑完成率、激活率），含 90 天 retention 清理。 | ✅ |
| `expert_summon.py` | 模块 | 专家召唤漏斗观测 API：写入 `surface_viewed/search_used/summon_attempted/summon_succeeded/summon_failed/route_applied/route_apply_failed/first_message_sent/dropped_report` 事件；聚合召唤成功率、路由应用率、首条发送转化率、use_case 触发率、搜索辅助率、失败原因分布，并做 90 天 retention 清理。 | ✅ |
| `growth_dashboard.py` | 模块 | Growth Dashboard API — aggregated view of agent growth metrics, cost/savings summary, and per-skill usage efficiency trends. | ✅ |
| `rate_limits.py` | 模块 | API endpoints for fetching real-time rate limit statistics | ✅ |
| `router.py` | 路由 | Base statistics routes: usage, daily, sessions, activity, tool-stability, badges（含 activeGoals 计数）. | ✅ |
| `session_analytics.py` | 模块 | 会话级分析 API。提供单个会话的详细统计（token、工具、事件时间线、任务指标）和执行追踪。 | ✅ |
| `turn_capability.py` | 模块 | 单轮 Skill/MCP 能力覆写观测 API：写入 selection/applied/noop/queue/completed/failed/busy-requeue/dropped 事件；`send_failed` 仅接受 `failure_reason` 枚举（`network_error/archive_restore_invalid/abort/server_error/unknown_error`）；聚合 apply/noop/queue/completion/failure 率、selected/effective 规模均值、source 分解与失败原因分布，并做 90 天 retention 清理。 | ✅ |
| `usage_aggregation.py` | 模块 | Coerce SQLAlchemy Row / tuple results into aggregate_usage inputs；聚合 token/cost/cache 指标并输出端到端 `streamTtft` 统计摘要（sampleCount/avg/p95，基于 `streamTtftMs` 样本，不依赖 usage 字段是否存在）。 | ✅ |
| `wiki_evidence.py` | 模块 | Wiki 证据链观测 API：写入 evidence_surface/snippet_open/snippet_close/query_attempted/query_submitted(success)/dropped_report/quality_outcome_negative 事件（支持 `context_key` 口径隔离；query 事件支持 `turn_distance` 观测；`quality_outcome_negative` 当前由含 KB 证据回答的 Regenerate/Undo 触发），聚合输出 snippet expansion、deep verification、re-query、quick bounce、dwell 与 negative outcome 指标，并新增 query attempt/success 成功率口径；内置 90 天 retention 周期清理；在 dropped/snippet/outcome 触发事件上评估治理告警，并通过系统通知+冷却去重（内存+DB）形成闭环。 | ✅ |
