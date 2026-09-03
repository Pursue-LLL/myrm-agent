# app/lifecycle 模块架构

应用生命周期编排层。按职责拆分为独立子模块，在启动/关闭时按序初始化和清理各系统组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `auto_continue.py` | 核心 | **InterruptedTurnMarker 普通回合崩溃自动续跑**：扫描 eligible markers（freshness 15min / max 2 attempts crash-loop breaker）并后台重跑（经 `build_agent_runtime_context` 注入 POOLED runtime context，且原子回放未消费持久化 Steering 消息）；流内收集 `message_end.token_economics` 作为消息 `extra_data` 持久化，与主路径共享消息级成本记账口径；成功/失败均创建 SystemNotification；finally 清理 marker | ✅ |
| `system.py` | 核心 | 启动编排：Channel Gateway 启动/关闭、RiskRule 内置规则播种、HITL 白名单持久化存储初始化、OfflineDurableTask 断点续跑（经 `build_agent_runtime_context` 注入 POOLED runtime context；成功/失败均创建 SystemNotification）、孤儿 Goal 自动暂停、IdleTask 进度事件转发到 ServerEventBus（含 CAPTURED 技能提案统一成长生命周期路由） | ✅ |
| `schedulers.py` | 核心 | 定时任务调度：Cron 启动（含 legacy `monitor_config` 启动批量清洗，批次数受限以保护冷启动时延，并输出续清状态日志）、Kanban Dispatcher 启动/关闭（含 Boot Recovery）、上下文清理(每日3:00)、DB维护(每6h: WAL checkpoint+备份+Qdrant优化+线程清理+Memory import cleanup+**async task queue cleanup**+Kanban GC+**Artifact share registry GC**+**Channel data plane GC**)、审批TTL(5min)、登录会话清理(5min)、审计日志归档(每日4:00)、ContextCompaction + `app/services/agent/memory_brief_telemetry/` MemoryBriefStatus + MemoryGuardianGuard 遥测分发器生命周期、**Kanban TaskSpecifier/TaskDecomposer 注入** | ✅ |
| `memory_guardian.py` | 核心 | 记忆守护者调度器。独立于用户会话的周期性记忆维护（频率档位驱动 1-8h 自适应）+ quiet window 运行窗口约束（窗口关闭时最多每 15 分钟复检一次，保证策略变更可生效）+ 每次维护后自动 SQLite 热备份 + 每 168h 委托 pattern_discovery_trigger 执行行为模式发现（周期间隔判定抽为可测纯函数 `_pattern_discovery_due`，`run_pattern_discovery_once`/`_run_pattern_discovery_cycle` 为薄委托）；手动触发维护支持 `safe/force` 双契约，safe 路径的活跃会话/预算/容量守卫均按 fail-closed 执行（守卫不可用即跳过并写入 WARNING 观测事件）。写侧审计事件位于 `app/services/memory/ledger/guardian_events.py`，维护子任务位于 `app/lifecycle/memory_guardian_ops.py`，本模块只负责调度与控制流 | ✅ |
| `memory_guardian_ops.py` | 辅助 | 记忆守护者维护子任务：过期归档记忆自动清理（TTL 7天）+ 超时冲突自动解决（低风险 72h 后 keep_old；high_risk 冲突无 auto_resolve_at 永不自动解决，需用户显式裁决；每次 auto-resolve 写入专属审计事件）+ 会话盲点自动收割（`harvest_session_blind_spots`：扫描未回答提问与用户纠偏信号，LLM 提炼知识补丁并写入 `knowledge_patch` 待审）+ `create_guardian_memory_manager` 守护者上下文 MemoryManager 工厂。纯数据操作，无调度状态依赖 | ✅ |
| `pattern_discovery_trigger.py` | 辅助 | 行为模式发现触发器。管理 Pattern Discovery 的定时/手动执行，用 WebUI 默认对话模型（`load_platform_llm` → wire-aware `ChatLiteLLM`）构造分析 LLM（guardian 上下文 MemoryManager 本身无 LLM），发现结果写入 operation_ledger 以供 Command Center 时间线和 Evolution Digest 展示；audit summary 为 toC 用户可读文案（耗时等内部细节仅保留在 metadata，不泄漏到时间线）；LLM 未配置时优雅跳过 | ✅ |
| `browser.py` | 核心 | 浏览器生命周期：池预热（config + proxy pool + launch_options）/关闭、线程清理、会话预热（可选）。代理池从 DB 配置或 `MYRM_PROXIES` 环境变量解析 | ✅ |
| `monitors.py` | 辅助 | 后台监控器（内存压力、认证告警） | ✅ |
| `harness_bridge.py` | 辅助 | 框架事件桥接器。监听 Harness 状态事件，debounce 合并 subagent 树并通过 `subagents_updated` 广播；`spawn`/`complete` 生命周期事件同步发布 `subagent_spawned`/`subagent_merged` 供出站 Webhook；关闭时释放 Harness 资源 | ✅ |
| `skills.py` | 辅助 | 技能系统初始化（发现、加载） | — |
| `task_worker.py` | 辅助 | 异步任务 worker 生命周期（SQLite 任务存储、Vault GC 定时清理） | ✅ |
