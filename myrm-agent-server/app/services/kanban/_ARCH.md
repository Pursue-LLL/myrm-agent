# services/kanban/ 模块架构

## 架构概述

Kanban 看板业务编排层。协调 Harness 的 KanbanStore/KanbanDispatcher 与 Server 层的
SqlAlchemy 持久化适配器，对 API 层暴露干净的业务 API。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 KanbanService | ❌ |
| `service.py` | ✅ 入口 | KanbanService 单例 facade（mixin 组合） | ✅ |
| `service_core.py` | ✅ 核心 | 单例状态、runner/specifier/decomposer 注入、`_wake_dispatcher`、agent 校验 | ❌ |
| `service_board_task_mixin.py` | ✅ 核心 | Board/Task 写操作薄壳 | ❌ |
| `service_query_dispatcher_mixin.py` | ✅ 核心 | 读查询薄壳 + dispatcher 生命周期（`KanbanReadMixin` / `KanbanDispatcherMixin`） | ❌ |
| `service_ai_mixin.py` | ✅ 核心 | specify/decompose 工作流薄壳（直连 orchestrator） | ❌ |
| `query_ops.py` | ✅ 核心 | Store 只读查询（含 `source_chat_id` / `project_id` 过滤）与 user comment | ❌ |
| `service_types.py` | ✅ 核心 | DTO/异常/常量 | ❌ |
| `event_publisher.py` | ✅ 核心 | SSE ServerEventBus 发布、`emit_btw_done`、`emit_source_chat_done`（completed/failed/blocked，scheduled block 跳过）、`emit_review_requested`（IN_REVIEW 进入时 pending_review 通知） | ❌ |
| `board_ops.py` | ✅ 核心 | Board CRUD + `project_id/milestone_id` 作用域校验与绑定 | ❌ |
| `task_ops.py` | ✅ 核心 | Task add/update/delete | ❌ |
| `move_orchestrator.py` | ✅ 核心 | move/reclaim/cancel 编排；IN_REVIEW 源/目标守卫（手动 move 绕过审批禁止） | ❌ |
| `review_ops.py` | ✅ 核心 | IN_REVIEW 审批编排：approve→COMPLETED（promote dependents）、reject→READY（reason 回写 error、retry_count 重置），优先委托 dispatcher，fallback 走 store 原子 CAS 流转 + 统一 action（task_completed/task_rejected）+ 完成通知补发；非 IN_REVIEW 幂等 no-op | ✅ |
| `dependency_ops.py` | ✅ 核心 | 依赖边 CRUD、promote | ❌ |
| `board_summary.py` | ✅ 核心 | `build_board_summary`（含 `stale_running_count`） | ❌ |
| `dispatcher_lifecycle.py` | ✅ 核心 | Dispatcher 启停、boot recovery；注册 task_completed/failed/blocked 与 task_review_requested 通知回调 | ❌ |
| `task_runner.py` | ✅ 核心 | KanbanTaskRunner 编排入口；worker 工具绑定 + goal-mode GoalProvider 注入；team protocol 与 **`profile_output_suffixes`**（人格 + `response_locale_policy`）注入 `user_instructions` 尾；注入 `event_log_dir` 使 kanban 任务写 event_log（供 RunsHub/看板 drawer trace 回放）；per-task `model_override` 优先于 agent profile 默认模型解析（override 无效时回退默认模型并记录 WARNING）；**`enable_memory` 遵循用户全局 `enableMemory` 开关（`resolve_memory_enabled`，与 channel/voice/cron 一致），看板无人值守任务不写用户已关闭的记忆** | ✅ |
| `kanban_attach_handler.py` | ✅ 核心 | Worker `kanban_attach` 回调：workspace 路径 + HTTPS URL（SSRF guard）→ files vault + task attachment_ids | ✅ |
| `task_runner_stream.py` | ✅ 核心 | Stream 累积、附件、multimodal query；PDF/Office 提取经 `files_service.get_content` SSOT | ❌ |
| `task_runner_worktree.py` | ✅ 核心 | Git worktree 隔离 | ❌ |
| `task_runner_profile.py` | ✅ 核心 | Agent profile 解析 | ❌ |
| `diagnostics.py` | ✅ 核心 | 诊断引擎工厂、摘要 | ✅ |
| `diagnostic_rules.py` | ✅ 核心 | 6 条诊断规则 | ❌ |
| `specifier.py` | ✅ 核心 | PlatformTaskSpecifier | ✅ |
| `specify_orchestrator.py` | ✅ 核心 | TRIAGE→spec 编排 | ✅ |
| `llm_utils.py` | ✅ 核心 | LLM 辅助工具（specifier/decomposer 共用） | ✅ |
| `decomposer.py` | ✅ 核心 | PlatformTaskDecomposer | ✅ |
| `decompose_orchestrator.py` | ✅ 核心 | TRIAGE→子任务图编排；子任务继承父任务 `source_chat_id` 与 `model_override` | ✅ |
| `pipeline_spec_io.py` | ✅ 核心 | Pipeline frontmatter 解析；`TaskSeed.repeat_for_item_skills` 按 repeat 项注入技能 | ✅ |
| `pipeline_instantiator.py` | ✅ 核心 | Pipeline 模板实例化；依赖父任务时继承 `source_chat_id`；`repeat_for_item_skills` 按平台注入 `extra_skill_ids` | ✅ |
| `gc.py` | ✅ 核心 | KanbanGCService 自动垃圾回收 | ✅ |

## 依赖关系

### 内部依赖
- `app/core/kanban/adapters/`：SqlAlchemyKanbanStore 持久化实现
- `app/services/event/app_event_bus`：AppEvent、AppEventType、get_event_bus（SSE 实时事件发布）
- `myrm_agent_harness/toolkits/kanban/`：KanbanDispatcher、TaskRunner Protocol、域类型、context_builder
- `myrm_agent_harness/toolkits/kanban/diagnostics`：诊断框架 DTO/Protocol/Engine
- `app/services/agent/profile_resolver`：AgentProfileResolver
- `app/services/files/attachment_settings`：`extractDocumentText` 开关
- `app/services/files/content_extraction`：PDF/Office 字节流提取
- `app/ai_agents/agents`：AgentFactory、GeneralAgentParams

### 被依赖方
- `app/api/kanban/`：HTTP 路由层调用 KanbanService、诊断引擎
- `app/services/agent/`：AgentService.delete_agent() 级联调用 clear_agent_references()
