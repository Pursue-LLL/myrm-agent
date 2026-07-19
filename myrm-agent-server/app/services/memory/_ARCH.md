# services/memory 模块架构


## 架构概述

记忆服务层。提供记忆数据备份/恢复、单用户 Memory Archive 导出与审查预检、单用户 Memory Archive 安全合并恢复与回滚账本、个人大脑指挥中心聚合、独立 Memory Diagnostics 探针、迁移完整性检查、诊断召回基准、结构化修复计划与白名单执行、导入 adapter 目录、服务端绑定导入审查会话、纯导入计划校验、关系型导入批次/条目事务账本、崩溃安全回滚 journal、导入后自动诊断、账本权威回滚预演与基于 exact mutation refs 的精准回滚、回滚后完整性探针、画像 revision 乐观并发保护、会话清理、记忆操作账本、影响证据分析，以及 Shared Context 共享上下文的产品层治理、记忆依赖健康检查、审批物化和历史证据提升能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `backup.py` | 核心 | 记忆数据备份与恢复服务 | — |
| `backup_remote.py` | 核心 | 远程备份策略模块。WebDAV/S3 云端备份的 upload/download/list/delete 抽象和实现 | ✅ |
| `backup_remote_scheduler.py` | 核心 | 远程备份自动同步调度。执行单次远程备份周期(创建→上传→轮转)和远程恢复流程 | ✅ |
| `backup_remote_utils.py` | 辅助 | 远程备份工具函数。桥接 VolumeBackupStrategy 与远程存储，提供可导出备份创建和恢复 | ✅ |
| `archive.py` | 核心 | 单用户 Memory Archive 服务。基于 Harness archive DTO 聚合普通记忆、Shared Context、会话、回放事件和记忆审计账本，执行内容脱敏并提供导入前结构校验，不包含多租户或控制平面语义 | ✅ |
| `archive_restore.py` | 核心 | 单用户 Memory Archive 恢复服务。提供归档分区 dry-run、payload/plan hash 强校验、恢复前安全预检、journaled safe-merge 恢复、关系型恢复账本、恢复后诊断 metadata 挂载、中断恢复回滚、profile 并发保护、Shared Context/会话/回放/审计恢复和精准回滚，不包含多租户或控制平面语义 | ✅ |
| `command_center.py` | 核心 | 个人大脑指挥中心聚合服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run，并支持强制刷新健康快照 | ✅ |
| `command_center_insights.py` | 核心 | 个人大脑指挥中心洞察服务。生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号、含导入回滚与归档恢复健康的部署边界摘要、迁移来源聚合、最近导入批次、导入后验证建议、自动诊断状态和导入审查清理指标 | ✅ |
| `diagnostic_probe_results.py` | 辅助 | Memory Diagnostics probe 结果归一化。集中处理 rollup、action 状态映射、impact/next action/auto-fix/retry 字段、repair plan 传递和静态检查到可执行探针的转换 | ✅ |
| `diagnostic_quality_governance.py` | 辅助 | Memory Doctor 质量治理探针。读取框架层 health score，返回内容不可见的新鲜度、覆盖率、保留健康和一致性证据 | ✅ |
| `diagnostic_recall_benchmark.py` | 辅助 | Memory Doctor 黄金召回基准。16 个合成 case（8 类别 × 中英双语），写入 semantic/episodic 记忆、检索 top-5、清理探针数据，返回 recall@5/ndcg@5/mrr/precision@5/latency_p50/p95、per-category 命中统计和结构化 MemoryCommandBenchmarkSummary | ✅ |
| `diagnostic_repair_executor.py` | 核心 | Memory Doctor 修复执行器。通过白名单执行 `run_diagnostics`、`run_health_refresh`，对配置类修复返回 blocked/manual 结果，避免自动改本地配置或读取业务记忆内容 | ✅ |
| `diagnostic_repair_plans.py` | 辅助 | Memory Doctor 修复计划目录。把 compact action id 映射为风险等级、dry-run、预期效果和可执行性，不修改配置、不读取业务记忆内容 | ✅ |
| `diagnostic_slo.py` | 辅助 | Memory Doctor 诊断 SLO 汇总。读取最近诊断审计事件的 metadata，计算窗口通过率、失败次数和平均耗时 | ✅ |
| `diagnostic_static_checks.py` | 辅助 | Memory Doctor 静态检查构建器。生成 relational store、memory path、vector index、knowledge graph、embedding provider、event ledger、health snapshot、deployment boundary 快照检查 | ✅ |
| `diagnostics.py` | 核心 | Memory Diagnostics 服务。生成 Memory Doctor 静态检查并执行 relational store、memory path、vector index、knowledge graph、embedding provider、embedding live、retrieval pipeline、sparse CJK recall、golden recall benchmark、memory quality governance、event ledger、migration integrity、health snapshot、deployment boundary 探针，写入不含业务内容的诊断审计事件并返回审计写入状态与诊断 SLO | ✅ |
| `import_adapter_registry.py` | 核心 | 记忆导入 adapter 目录。为导入 dry-run 和个人大脑指挥中心提供一致的来源支持状态，标记 native-json/myrm-archive/agentmemory/claude-code/hermes/openclaw/cursor/codex/chatgpt ready 与其他来源计划或缺失状态 | ✅ |
| `import_adapters.py` | 核心 | 记忆导入 dry-run dispatcher。Wizard 五源 `_MIGRATION_SOURCE_TO_ADAPTER`（含 chatgpt upload-only）；Memory Center 手动导入仍支持 cursor_rules/mem0 等；`_source` 标签优先于 Markdown 启发式 | ✅ |
| `import_adapter_utils.py` | 辅助 | 导入适配器共享工具。集中 `build_result`、`unsupported_result`、`object_dict`、`text` 和 warning code 常量 | ✅ |
| `import_native_json.py` | 辅助 | Native JSON 导入解析器。处理原生 JSON 格式导入映射 | ✅ |
| `import_agentmemory.py` | 辅助 | AgentMemory 导入解析器。处理 agentmemory export 格式解析 | ✅ |
| `import_myrm_archive.py` | 辅助 | Myrm Archive 导入解析器。处理 Myrm Memory Archive 的 memory section | ✅ |
| `import_claude_code.py` | 辅助 | Claude Code JSONL 导入解析器。调用 claude_code_parser 消费 JSONL transcript | ✅ |
| `import_claude_code_parser.py` | 辅助 | Claude Code JSONL transcript 解析器。逐行解析 JSONL entry、id 去重（last-write-wins）、entry 分类（user/assistant/summary/system）、对话 turn 重建、summary→semantic / turn→episodic / error→procedural 映射 | ✅ |
| `import_hermes.py` | 辅助 | Hermes 记忆车道解析器。MEMORY.md/USER.md → semantic/profile；SOUL/AGENTS 由 migration 指令车道处理 | ✅ |
| `import_openclaw.py` | 辅助 | OpenClaw 竞品导入解析器。解析 OpenClaw sessions 和 memory entries | ✅ |
| `import_cursor.py` | 辅助 | Cursor 竞品导入解析器。解析 Cursor rules 和 settings 到原生记忆类型 | ✅ |
| `import_codex.py` | 辅助 | Codex 竞品导入解析器。解析 Codex instructions 和 settings 到原生记忆类型 | ✅ |
| `import_chatgpt.py` | 辅助 | ChatGPT 竞品导入解析器。解析 ChatGPT conversations.json 的 tree-based mapping 结构到 episodic 记忆类型 | ✅ |
| `import_sessions.py` | 核心 | 记忆导入审查会话编排服务。持久化 dry-run 结果、payload hash、过期时间、normalized data 和 plan hash，确认时只接受 dry_run_id 并校验计划一致性，协调导入批次审计、迁移来源、关系型 item-level transaction ledger、崩溃安全回滚 journal、账本权威回滚预演、profile revision 冲突保护、回滚后完整性探针、导入后诊断结果回写和保留窗口清理指标 | ✅ |
| `import_session_data.py` | 辅助 | 记忆导入会话数据转换。负责 payload 指纹、纯导入计划、normalized data JSON 转换、导入 metadata 注入、transaction item 构建和 profile 导入前后 revision snapshot 采集 | ✅ |
| `import_session_models.py` | 辅助 | 记忆导入会话 DTO。定义 confirm、rollback preview 和含 exact ref drilldown / integrity status 的 rollback result 服务层返回对象 | ✅ |
| `import_ledger.py` | 核心 | 记忆导入批次/条目事务账本服务。维护 confirmed/rollback_in_progress/rolled_back/partial/rollback_failed 批次状态和 imported/skipped/rolled_back/conflict/missing/rollback_failed 条目状态，保存内容盲回滚事实、结构化 warning code、rollback health counter 和自动诊断摘要 | ✅ |
| `import_rollback.py` | 核心 | 记忆导入回滚辅助。封装账本条目分类、profile revision 并发冲突检测、结构化 warning 生成、普通记忆 exact mutation refs 回滚和 profile 乐观回滚 | ✅ |
| `command_center_projection_utils.py` | 辅助 | 个人大脑指挥中心投影辅助。集中维护阶段映射、瀑布流状态、预览、数值解析和 eval metric 构建，避免洞察服务膨胀 | ✅ |
| `guardian_policy.py` | 核心 | Memory Guardian 调度策略服务。持久化 `frequency_tier`/`quiet_window` 配置，提供运行窗口判定与下次窗口开启时间计算，并记录 `timezone_source`；首访时完成浏览器时区初始化，无浏览器时区头时由 API 使用服务端本地时区兜底，后续收到真实客户端时区头时可自动纠偏 | ✅ |
| `operation_ledger.py` | 核心 | 单用户记忆操作账本服务。持久化记忆事件、健康快照缓存和外部记忆导入来源；`record_event` 同步发布 `memory_operation` SSE；提供 `list_events_for_session` 供 Session Replay memory_events 叠加查询，并提供 Guardian 晨间摘要按维护窗口聚合读取与守卫不可用告警聚合快照（按 frequency tier 自适应最小事件阈值 + escalation 阈值元数据） | ✅ |
| `manager_deps.py` | ✅ 辅助 | MemoryManager FastAPI 依赖工厂（`get_memory_manager` / `get_crud_memory_manager` / `get_optional_memory_manager`） | ✅ |
| `presentation.py` | ✅ 辅助 | 记忆实体→`MemoryItem` DTO 转换与 `parse_memory_type` 校验 | ✅ |
| `shared_context.py` | 核心 | Shared Context 共享上下文服务。管理上下文 CRUD、绑定解析、写入提案生命周期（goal_completion / correction_propagation 幂等 dedup）及治理 policy | ✅ |
| `shared_context_health.py` | 核心 | Shared Context 记忆健康服务。安全检查 embedding 配置并支持实时探测，供 UI、API 和 smoke 验证复用 | ✅ |
| `shared_context_history.py` | 核心 | Shared Context 历史证据服务。复用会话历史搜索并构建历史消息提升提案的来源元数据 | ✅ |
| `shared_context_materializer.py` | 核心 | Shared Context 写入物化服务。批准 proposal 后幂等写入目标 shared namespace，并附加审计元数据 | ✅ |
| `integration_memory.py` | 核心 | Integration Memory 业务服务。封装框架层 IntegrationFetcher/TreeManager/Summariser，提供 sync/browse/status/remove facade 和类型安全 DTO（IntegrationStatusSnapshot/IntegrationTreeNodeDTO）供 API 层消费 | ✅ |
| `mcp_bridge_provider.py` | 核心 | MCPBridgeProvider — 将任意 MCP Server 桥接为 IntegrationProvider。通过 DI 注入 MCPConnection，自动探测 fetch 工具并将结果转换为 IntegrationLeaf | ✅ |
| `integration_sync_daemon.py` | 核心 | Integration Sync Daemon — 基于 APScheduler 的后台定时同步守护进程。每次触发时动态加载用户 MCP 配置，将符合条件的 MCP Server 注册为 MCPBridgeProvider，然后调用 IntegrationMemoryService.sync_all() 保持知识源新鲜 | ✅ |
