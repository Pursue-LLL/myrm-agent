# app/lifecycle 模块架构

应用生命周期编排层。按职责拆分为独立子模块，在启动/关闭时按序初始化和清理各系统组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `auto_continue.py` | 核心 | **InterruptedTurnMarker 普通回合崩溃自动续跑**：扫描 eligible markers（freshness 15min / max 2 attempts crash-loop breaker）并后台重跑（在 `server_turn_lease` 下运行：先占会话并注册取消令牌，会话已被消息占用则不重放、按失败通知处理，聊天「停止」与 E-Stop 能到达重放回合；回复文本经 `AnswerDraft` 累积；经 `build_agent_runtime_context` 注入 POOLED runtime context，且原子回放未消费持久化 Steering 消息；历史加载排除 marker 记录的已落库用户行 `user_message_id`，避免与回放 query 重复；以 `history_mode=replace` 重建线程，被中断那一轮留在线程里的半截状态不会和回放叠加）；流内收集 `message_end.token_economics` 作为消息 `extra_data` 持久化，与主路径共享消息级成本记账口径；成功/失败均创建 SystemNotification；finally 清理 marker | ✅ |
| `risk_rules.py` | 核心 | 启动风险规则初始化：播种内置 RiskRule，再重载检测引擎；先读后写的事务若被并发启动写入方抢先提交，SQLite 会立刻报 `database is locked` 且不受 busy_timeout 约束，故失败时用新事务重试，最多 3 次；仍未载入时由 `RiskDetectionService.ensure_loaded` 在首段用户文字过闸时补载入，进程不会放行到重启 | ✅ |
| `system.py` | 核心 | 启动编排：Channel Gateway 启动/关闭、HITL 白名单持久化存储初始化、孤儿 Goal 自动暂停、IdleTask 进度事件转发到 ServerEventBus | ✅ |
| `schedulers/` | 子包 | 生命周期调度器，按对象分 7 个模块（cron / context / maintenance / security / kanban / backup + common）：Cron 启动与 legacy monitor 批量清洗、上下文清理与遥测 dispatcher、数据库维护（WAL/共享库 GC/浏览器会话 GC/无痕清理/checkpoint 裁剪/实例备份）、审批 TTL 与令牌清理、Kanban dispatcher、远程备份检查。见 [schedulers/_ARCH.md](schedulers/_ARCH.md) | ✅ |
| `memory_guardian.py` | 核心 | 记忆守护者 Facade。封装 `CognitiveClockCoordinator` 的自适应维护调用，提供向后兼容的手动触发与安全门禁拦截，保证外部调用方无感桥接 | ✅ |
| `cognitive_clock/` | 核心 | 嵌套多频认知时钟中枢（T0 微步、T1 会话防抖提炼、T2 闲时固化、T3 历元自进化），集成用户打字避让传感器与唤醒平滑防洪门禁 | [cognitive_clock/_ARCH.md](cognitive_clock/_ARCH.md) |
| `memory_guardian_ops.py` | 辅助 | 记忆守护者维护子任务：过期归档记忆自动清理（TTL 7天）+ 超时冲突自动解决（低风险 72h 后 keep_old；high_risk 冲突无 auto_resolve_at 永不自动解决，需用户显式裁决；每次 auto-resolve 写入专属审计事件）+ 会话盲点自动收割（`harvest_session_blind_spots`：扫描未回答提问与用户纠偏信号，LLM 提炼知识补丁并写入 `knowledge_patch` 待审，审批原因按用户语言取自渠道文案目录 `knowledge_patch_review_reason`）+ `create_guardian_memory_manager` 守护者上下文 MemoryManager 工厂（携带后台演化模型作为整合 LLM，整合与过期复核共用；`load_platform_evolution_llm` 演化→轻量→主模型三层降级，加载失败时记 WARNING，并由 MemoryManager 工厂回退到去重模型）+ `run_sqlite_backup` 维护周期末尾的应用 SQLite 热备份（页拷贝为阻塞 I/O，经 `asyncio.to_thread` 脱离事件循环；失败仅记 WARNING，不使维护周期失败）。纯数据操作，无调度状态依赖 | ✅ |
| `pattern_discovery_trigger.py` | 辅助 | 行为模式发现触发器。管理 Pattern Discovery 的定时/手动执行，用 WebUI 后台自进化模型（`load_platform_evolution_llm` → wire-aware `ChatLiteLLM`，带三层自适应降级）构造分析 LLM（`_build_platform_llm`，`streaming=False, temperature=0.0`），与 guardian 上下文 MemoryManager 一并传入 `run_pattern_discovery(manager, llm)`；manager 经工厂另行携带自己的演化模型，pattern discovery 的 LLM 依赖独立于维护预算策略，发现结果写入 operation_ledger 以供 Command Center 时间线和 Evolution Digest 展示；audit summary 为 toC 用户可读文案（耗时等内部细节仅保留在 metadata，不泄漏到时间线）；LLM 未配置时优雅跳过 | ✅ |
| `browser.py` | 核心 | 浏览器生命周期：池预热（config + proxy pool + launch_options）/关闭。代理池从 DB 配置或 `MYRM_PROXIES` 环境变量解析 | ✅ |
| `monitors.py` | 辅助 | 后台监控器（内存压力、认证告警） | ✅ |
| `harness_bridge.py` | 辅助 | 框架事件桥接器。监听 Harness 状态事件，debounce 合并 subagent 树并通过 `subagents_updated` 广播；`spawn`/`complete` 生命周期事件同步发布 `subagent_spawned`/`subagent_merged` 供出站 Webhook；关闭时释放 Harness 资源 | ✅ |
| `task_worker.py` | 辅助 | 异步任务 worker 生命周期（SQLite 任务存储、持有 claim 循环任务并在停止时等待收尾、`get_task_worker()`、Vault GC 定时清理） | ✅ |
