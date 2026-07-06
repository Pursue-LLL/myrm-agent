# app/lifecycle 模块架构

应用生命周期编排层。按职责拆分为独立子模块，在启动/关闭时按序初始化和清理各系统组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `system.py` | 核心 | Channel Gateway 启动/关闭编排 | — |
| `schedulers.py` | 核心 | 定时任务调度：Cron 启动、Kanban Dispatcher 启动/关闭（含 Boot Recovery）、上下文清理(每日3:00)、DB维护(每6h: WAL checkpoint+备份+Qdrant优化+线程清理+Memory import cleanup+**async task queue cleanup**+Kanban GC)、审批TTL(5min)、登录会话清理(5min)、审计日志归档(每日4:00)、**Kanban TaskSpecifier/TaskDecomposer 注入** | ✅ |
| `memory_guardian.py` | 核心 | 记忆守护者调度器。独立于用户会话的周期性记忆维护（自适应频率 2-6h）+ 过期归档记忆自动清理（TTL 7天）+ 超时冲突自动解决（72h 后 keep_old）+ 每次维护后自动 SQLite 热备份 + 维护结果审计事件写入 operation_ledger（SSE 推送到 Command Center）+ 每 168h 委托 pattern_discovery_trigger 执行行为模式发现，手动触发支持维护和模式发现两个独立入口，调度器路径保留活跃会话/预算/容量三重安全守卫 | ✅ |
| `pattern_discovery_trigger.py` | 辅助 | 行为模式发现触发器。管理 Pattern Discovery 的定时/手动执行，将结果写入 operation_ledger 以供 Command Center 时间线和 Evolution Digest 展示 | ✅ |
| `browser.py` | 核心 | 浏览器生命周期：池预热（config + proxy pool + launch_options）/关闭、线程清理、会话预热（可选）。代理池从 DB 配置或 `MYRM_PROXIES` 环境变量解析 | ✅ |
| `monitors.py` | 辅助 | 后台监控器（内存压力、认证告警、健康历史等） | — |
| `harness_bridge.py` | 辅助 | 框架事件桥接器。监听 Harness 状态事件，debounce 合并 subagent 树并通过 `subagents_updated` 广播（`chat_id` 经 `session_tree._normalize_rest_chat_id` 归一为 REST uuid，含重复 `chat_` 前缀）；关闭时释放 Harness 资源 | ✅ |
| `skills.py` | 辅助 | 技能系统初始化（发现、加载） | — |
| `task_worker.py` | 辅助 | 异步任务 worker 生命周期（SQLite 任务存储、Vault GC 定时清理） | ✅ |
