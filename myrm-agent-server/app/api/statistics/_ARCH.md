# Statistics API Module

## 架构概述

统计API模块，聚合Message.extra_data、Chat压缩元数据和EventLog数据，提供Token使用分析、Session详情API、结构化 `context_health` 健康视图，以及 Growth Dashboard 成长仪表盘。

核心能力：
1. 全局统计：/usage（总Token、费用、模型分布）
2. Session统计：/usage/sessions（按会话分组）
3. 日度统计：/usage/daily（时间序列数据）
4. 模型统计：/usage/models（模型维度分布）
5. **Session详情**：/session/{session_id}（单会话完整analytics，含工具使用、事件时间线、`context_health`）
6. **Growth Dashboard**：/growth-dashboard（Agent成长仪表盘，聚合记忆、活跃度、统一技能成长时间线、周摘要）

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|-----|-------|
| router.py | 核心 | Statistics API 主路由（usage/daily/activity/badges 等） | ✅ |
| session_analytics.py | 核心 | 会话级分析 API（session analytics + execution trace） | ✅ |
| growth_dashboard.py | 核心 | Growth Dashboard 聚合API（记忆统计、活跃度热力图、技能进化状态分组统计、统一技能成长时间线、周摘要） | ✅ |
| context_health.py | 核心 | 将 Message usage、Chat 压缩元数据、Harness task_metrics 聚合为结构化 `context_health`（压缩、cache-TTL 剪枝、归档摘要 checkpoint、归档、恢复请求/放行/阻断、恢复结果 ROI、恢复成本告警、自适应剪枝退让、Prompt Cache 健康） | ✅ |
| context_health_cache.py | 核心 | Prompt Cache 健康采样：provider-aware retention policy、主模型优先/精确归一匹配、保留信号样本和 cache hit 状态判定 | ✅ |
| context_health_restore.py | 核心 | 恢复阻断事件清洗：结构化恢复范围提示、内容结构特征、restore guidance source 与 fallback reason 的 UI 安全 DTO | ✅ |
| daily_journal.py | 核心 | 每日工作日志 API（跨 session/approval/cron/kanban/EventLog 聚合的日级时间线视图） | ✅ |
| usage_aggregation.py | 核心 | Message.extra_data usage 聚合器（daily/session/global 共用，支持按日汇总 Token、精确的 USD 缓存节省金额、以及拦截聚合各类 Cache Break 归因计数） | ✅ |
| __init__.py | 辅助 | 路由注册（合并 router + growth_dashboard） | - |

## 核心端点

### 1. GET /api/v1/statistics/usage
- 全局Token使用统计（总输入/输出/缓存Token、费用、模型分布）

### 1b. GET /api/v1/statistics/usage/radar
- **BYOK 模式全局资源消耗雷达**（O(1) 复杂度聚合查询）
- 直接汇算 `Chat` 表级 `total_calls`, `total_tokens`, `total_usd`，为大盘提供极速响应

### 2. GET /api/v1/statistics/usage/sessions
- 按Session分组的使用统计（支持时间范围、排序、分页）

### 3. GET /api/v1/statistics/usage/daily
- 日度使用统计（时间序列数据，支持时间范围过滤，提供 Cache Hit Rate 趋势、USD 缓存节省金额趋势、以及历史 Cache Break 诊断时间线事件统计）

### 4. GET /api/v1/statistics/usage/models
- 模型维度统计（Token和费用按模型分组）

### 5. GET /api/v1/statistics/session/{session_id}
- **单会话详情analytics**（Session元数据、消息统计、Token/Cost、工具使用明细、事件时间线、`context_health`）
- **并发查询优化**（asyncio.gather 3数据源：Chat、Message、**harness EventLogger**）
- **Bug防护**（Session所有权验证 + EventLog缺失降级）
- **架构优化**：使用 `harness.EventLogger.get_session_summary()` 获取EventLog数据（框架层开箱即用），并在 Server 层集中完成健康语义聚合，包含 cache-TTL 剪枝预算延期原因、归档恢复 outcome 指标、恢复成本告警、自适应剪枝退让和 provider-aware retention policy，避免前端解析底层 task_metrics 细节

### 5b. GET /api/v1/statistics/session/{session_id}/trace
- **任务级执行回放**（结构化 ExecutionTrace：输入 → 工具调用序列（含 input_data/output_data）→ LLM 调用帧（含 start/end、prompt_preview）→ 人工审批 → 记忆事件叠加（memory_events）→ 错误 → 输出）
- 使用 `harness.trace_builder.build_trace()` 从原始事件流构建完整回放视图
- Session所有权验证 + EventLog缺失降级
- 前端 `ExecutionTraceTimeline` + `SessionReplayPlayer` 的数据源

### 6. GET /api/v1/statistics/daily-journal
- **每日工作日志**（单端点聚合，零新存储）
- 参数：`date=YYYY-MM-DD`（必填）、`agent_id`（可选，按智能体过滤）
- 顺序查询 DB 数据源（Chat, Message, ApprovalRecord, CronRunModel, KanbanTaskEventModel），并行查询 EventLog（非 DB，无 session 竞争）
- 返回：日级概览（sessions/tokens/cost/tool_calls/approvals/cron_runs/kanban_events/sessions_by_source）
- 返回：分项列表（sessions, approvals, cron_runs, kanban_events）
- 返回：混合时间线（所有事件按时间排序的统一 timeline）

### 7. GET /api/v1/statistics/growth-dashboard
- **Agent成长仪表盘**（单端点聚合，零新存储）
- KPI快照：记忆总量（按类型分布）+ 周增量（过去7天新增记忆数）、技能数+进化次数、活跃天数+连续Streak、记忆健康度评分
- 活跃度热力图：12周GitHub风格session计数
- 本周摘要：对话数、消息数、cron执行数、工具调用数 — 每项均含上周对比数据(previous_*)用于前端delta展示
- 技能成长时间线：最近20条成长事件（待审核 / 自动应用 / 批准 / 拒绝 / 应用失败 / 锁定 / 扫描失败）
- 记忆健康雷达：4维评分（活跃度/知识广度/记忆质量/一致性）
- **并发聚合**：asyncio.gather 4数据源（Memory Manager, EventLog, Skill Growth Query Service, DB）
- **架构**：Harness层零侵入，Server 层通过统一技能成长查询服务聚合技能成长时间线

## 数据源

1. **Message.extra_data**：存储每条assistant消息的usage元数据（input_tokens, output_tokens, cached_tokens, cost, cache_savings_usd, cache_break事件等）
2. **Chat**：存储Session元数据和压缩持久化状态（title, action_mode, compacted_at, compacted_tokens_saved）
3. **EventLog**：存储Session事件流（tool_start, tool_end, session_end等），并在 `session_end.summary.task_metrics` 中保留 Harness 级压缩指标

## 技术特性

- **并发聚合**：使用asyncio.gather()并发查询多数据源（提升响应速度）
- **单租户隔离**：通过沙箱模式确保数据完全隔离
- **优雅降级**：EventLog文件缺失时返回空数据而非报错
- **模型分组**：支持按模型名称分组统计（model_breakdown）
- **时间过滤**：支持start_date和end_date范围查询

## 依赖模块

- `app.database.models` - Message和Chat实体模型
- `myrm_agent_harness.agent.event_log` - 事件日志分析
  - **`EventLogger.get_session_summary()`** - 框架层会话analytics能力（开箱即用）
  - **`trace_builder.build_trace()`** - 任务级完整回放构建
  - `EventLogAnalytics.get_global_activity_patterns()` - 全局活跃度分析（Growth Dashboard使用）
  - `FileEventLogBackend` - 文件型EventLog后端
- `myrm_agent_harness.toolkits.memory` - 记忆管理（Growth Dashboard使用：count_memories, compute_health_score）
- `app.services.skills.growth_queries` - 统一技能成长查询（Growth Dashboard使用：成长时间线）
- `app.core.skills.store.service` - 技能清单服务（Growth Dashboard使用：技能总量）
- `app.core.memory.adapters.setup` - 记忆管理器工厂
- `app.core.cron.adapters.setup` - Cron管理器工厂（Growth Dashboard周摘要）
- `app.api.dependencies` - 沙箱环境认证
