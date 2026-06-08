
# app/lifecycle 模块架构

应用生命周期编排层。按职责拆分为独立子模块，在启动/关闭时按序初始化和清理各系统组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `system.py` | 核心 | Channel Gateway 启动/关闭编排 | ⚠️ 待补 |
| `schedulers.py` | 核心 | 定时任务调度：Cron 启动、Kanban Dispatcher 启动/关闭（含 Boot Recovery）、上下文清理(每日3:00)、DB维护(每6h: WAL checkpoint+备份+Qdrant优化+线程清理)、审批TTL(5min)、登录会话清理(5min)、审计日志归档(每日4:00)、**Kanban TaskSpecifier/TaskDecomposer 注入** | ✅ |
| `memory_guardian.py` | 核心 | 记忆守护者调度器。独立于用户会话的周期性记忆维护（自适应频率 2-6h）+ 过期归档记忆自动清理（TTL 7天）+ 每次维护后自动 SQLite 热备份 + 维护结果审计事件写入 operation_ledger（SSE 推送到 Command Center），手动触发会直接执行一次完整维护，调度器路径保留活跃会话/预算/容量三重安全守卫 | ✅ |
| `browser.py` | 核心 | 浏览器生命周期：池预热（config + local launch_options）/关闭、线程清理、会话预热（可选） | ✅ |
| `monitors.py` | 辅助 | 后台监控器（内存压力、认证告警、健康历史等） | ⚠️ 待补 |
| `harness_bridge.py` | 辅助 | 框架事件桥接器。监听 Harness 状态事件与 SkillFailureEvent，将 subagent 生命周期/策略拒绝状态广播为 AppEvent，并把技能失败证据交给 Server 免疫服务处理；关闭时经 `close_harness_resources` 统一释放 Harness 资源（事件总线 + MCP 持久连接池） | ✅ |
| `skills.py` | 辅助 | 技能系统初始化（发现、加载） | ⚠️ 待补 |
| `task_worker.py` | 辅助 | 异步任务 worker 生命周期（SQLite 任务存储、Vault GC 定时清理） | ✅ |
