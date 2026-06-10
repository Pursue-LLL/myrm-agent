# services/kanban/ 模块架构

## 架构概述

Kanban 看板业务编排层。协调 Harness 的 KanbanStore/KanbanDispatcher 与 Server 层的
SqlAlchemy 持久化适配器，对 API 层暴露干净的业务 API。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 KanbanService | ✅ |
| `service.py` | ✅ 核心 | 业务编排（Board/Task CRUD、依赖管理与自动提升、`move_task(force=True)` 强制跳过依赖+PROMOTED 审计事件、**`move_task` RUNNING→非终态时自动触发 RECLAIMED 事件+关闭活跃 run+清理 heartbeat/progress（reclaim 完整性）**、**`reclaim_task` 手动回收 RUNNING 任务：cancel worker+关闭 run+重置 READY+可选 reassign agent（原子化操作）+ASSIGNED 审计事件**、**`cancel_task_execution` 即时取消执行中的 asyncio.Task（不修改任务状态，配合 move_task 使用）**、`promote_task(force)` 手动提升 BACKLOG→READY 含 dry-run 与强制覆盖未完成父依赖、`DependencyUnmetError` 依赖未满足异常（含 `unmet_details` 父任务详情内联）、Dispatcher 生命周期、Boot Recovery、Run/Event 查询、摘要统计含 by_agent 分布与 oldest_ready_age、全量边查询、Agent 引用级联清理、SSE EventBus 实时事件发布、恢复语义：BLOCKED→READY 与 agent 变更时清零 failure 计数、agent_id 引用完整性校验+`update_task` agent_id 变更时自动发 ASSIGNED 审计事件、**多分支元数据级联更新 `update_active_tasks_branch_metadata`**、**TaskSpecifier 注入与 specify_task/specify_all_triage 薄壳代理**、**TRIAGE 出口转换 `_TRIAGE_ALLOWED_TARGETS` 强制**、**add_task `initial_status` 入参**、**`_emit_btw_done` 回调：/btw 任务终态时发布 `BACKGROUND_TASK_DONE` 事件到 EventBus 供 BtwTaskNotifier 消费**），BoardSummaryData/PromoteResult 强类型返回 | ✅ |
| `task_runner.py` | ✅ 核心 | TaskRunner Protocol 实现 — 桥接 KanbanTask → AgentProfileResolver → AgentFactory → GeneralAgent，Stream 事件累积，YOLO 模式自动启用，共享内存上下文解析，多模态附件处理（图片→image_url；PDF/Office 受 `personalSettings.extractDocumentText` 控制：开启则 `content_extraction` 注入正文，失败或无文本则 `[Attachment: filename]`），**Git worktree 隔离**，/btw 后台任务运行时 token 注册/注销 | ✅ |
| `diagnostics.py` | ✅ 核心 | 5 条诊断规则实现（stranded_in_ready / repeated_failures / stuck_in_blocked / dead_dependency / **stranded_in_triage**）、动态严重度升级、引擎工厂、摘要计算 | ✅ |
| `specifier.py` | ✅ 核心 | `PlatformTaskSpecifier` — TaskSpecifier 协议实现，复用 WebUI 配置的 LiteLLM 模型，CJK 自适应中英文系统提示词，三层降级容错（LLM 不可用 / 网络错误 / JSON 解析失败均返回 SpecifyOutcome(ok=False) 而非抛异常） | ✅ |
| `specify_orchestrator.py` | ✅ 核心 | TRIAGE→spec 编排逻辑（`run_specify_task` 预览/直接持久化、`run_apply_spec` 持久化缓存的 dry-run 结果避免 LLM 双调用、race-loss 保护、original_title/description metadata 留痕、SPECIFIED/PROMOTED 双事件、dispatcher.wake() 即时调度、`asyncio.Semaphore` 限流的 specify-all 批量扫描）— 单一职责模块，KanbanService 仅做薄壳代理 | ✅ |
| `llm_utils.py` | ✅ 核心 | LLM 辅助调用公共工具函数（`truncate`、`has_cjk`、`extract_json_blob`、`extract_usage`），被 specifier/decomposer 共用，DRY 原则 | ✅ |
| `decomposer.py` | ✅ 核心 | `PlatformTaskDecomposer` — TaskDecomposer 协议实现，复用 WebUI 配置的 LiteLLM 模型，CJK 自适应中英文系统提示词，roster 上下文注入，assignee 归一化，三层降级容错 | ✅ |
| `decompose_orchestrator.py` | ✅ 核心 | TRIAGE→子任务图编排逻辑（`run_decompose_task` 预览、`run_apply_decompose` 原子创建子任务+依赖边+DECOMPOSED 事件、`run_apply_no_fanout` fanout=false 降级为 Specify（TRIAGE→READY）、`build_agent_roster` roster 构建、parent_indices→task_id 映射、dispatcher.wake() 即时调度） | ✅ |
| `pipeline_instantiator.py` | ✅ 核心 | Pipeline 模板实例化服务 — 发现/加载 pipeline 类型 prebuilt skills、解析 pipeline_spec frontmatter（含 task_graph_variants）、确定性字符串模板替换、role→agent 匹配、批量创建 Kanban 任务图（tasks + edges）。零 LLM 调用，纯确定性。支持严格的 variant_id 校验与空图防御。 | ✅ |
| `gc.py` | ✅ 核心 | `KanbanGCService` — 三层自动垃圾回收（events/runs/workspaces），分批删除避免长锁，harness_dir 路径安全校验防穿越，统计日志。由 `_db_maintenance_job`（每6小时）和启动 warmup 调用。 | ✅ |

## 依赖关系

### 内部依赖
- `app/core/kanban/adapters/`：SqlAlchemyKanbanStore 持久化实现
- `app/api/events/event_bus`：AppEvent、AppEventType、get_event_bus（SSE 实时事件发布）
- `myrm_agent_harness/toolkits/kanban/`：KanbanDispatcher、TaskRunner Protocol、域类型、context_builder
- `myrm_agent_harness/toolkits/kanban/diagnostics`：诊断框架 DTO/Protocol/Engine
- `app/services/agent/profile_resolver`：AgentProfileResolver（agent profile 解析）
- `app/services/files/attachment_settings`：`extractDocumentText` 开关（Kanban 与渠道共用）
- `app/services/files/content_extraction`：PDF/Office 字节流提取
- `app/ai_agents/agents`：AgentFactory、GeneralAgentParams（agent 创建）

### 被依赖方
- `app/api/kanban/`：HTTP 路由层调用 KanbanService、诊断引擎
- `app/services/agent/`：AgentService.delete_agent() 级联调用 clear_agent_references()；_validate_agent_id() 依赖 AgentService.get_agent_by_id() 校验 agent 存在性
