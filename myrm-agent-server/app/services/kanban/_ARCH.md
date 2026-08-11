# services/kanban/ 模块架构

## 架构概述

Kanban 看板业务编排层。协调 Harness 的 KanbanStore/KanbanDispatcher 与 Server 层的
SqlAlchemy 持久化适配器，对 API 层暴露干净的业务 API。根目录仅含门面与单域模块；
同域实现细节分别位于 `task_runner/`、`service_mixins/`、`diagnostics/`、`pipeline/`、
`decompose/`、`specify/` 六个子包。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 KanbanService | ❌ |
| `service.py` | ✅ 入口 | KanbanService 单例 facade（mixin 组合） | ✅ |
| `service_mixins/` | ✅ 子包 | KanbanService 组合域（聚合入口被 service.py 门面与包根 `__init__.py` 消费；根操作模块因 mixin 依赖链须穿透 `.types`，见其 `__init__.py` IMPORT CONSTRAINT） | - |
| ├─ `core.py` | ✅ 核心 | 单例状态、runner/specifier/decomposer 注入、`_wake_dispatcher`、agent 校验 | ❌ |
| ├─ `types.py` | ✅ 核心 | DTO/异常/常量 | ❌ |
| ├─ `ai_mixin.py` | ✅ 核心 | specify/decompose 工作流薄壳（直连 orchestrator） | ❌ |
| ├─ `board_task_mixin.py` | ✅ 核心 | Board/Task 写操作薄壳（`update_board` 透传 `dispatchers` 使 settings 变更热生效） | ❌ |
| └─ `query_dispatcher_mixin.py` | ✅ 核心 | 读查询薄壳 + dispatcher 生命周期（`KanbanReadMixin` / `KanbanDispatcherMixin`） | ❌ |
| `task_runner/` | ✅ 子包 | TaskRunner 执行域（聚合出口见其 `__init__.py`） | - |
| ├─ `runner.py` | ✅ 核心 | KanbanTaskRunner 编排入口；worker 工具绑定 + goal-mode GoalProvider 注入；team protocol 与 **`profile_output_suffixes`**（人格 + `response_locale_policy`）注入 `user_instructions` 尾；注入 `event_log_dir` 使 kanban 任务写 event_log（供 RunsHub/看板 drawer trace 回放）；per-task `model_override` 优先于 agent profile 默认模型解析（override 无效时回退默认模型并记录 WARNING）；**`enable_memory` 遵循用户全局 `enableMemory` 开关（`resolve_memory_enabled`，与 channel/voice/cron 一致），看板无人值守任务不写用户已关闭的记忆** | ✅ |
| ├─ `stream.py` | ✅ 核心 | Stream 累积、附件、multimodal query；PDF/Office 提取经 `files_service.get_content` SSOT | ❌ |
| ├─ `worktree.py` | ✅ 核心 | Git worktree 隔离 | ❌ |
| └─ `profile.py` | ✅ 核心 | Agent profile 解析 | ❌ |
| `diagnostics/` | ✅ 子包 | 诊断域（聚合出口即 `__init__.py`，保留原 `diagnostics.py` 公共 API） | - |
| ├─ `__init__.py` | ✅ 核心 | 诊断引擎工厂、摘要（`create_diagnostic_engine`、`CARD_FAST_RULES`、`compute_diagnostics_summary`） | ✅ |
| ├─ `rules.py` | ✅ 核心 | 5 条诊断规则（滞留/失败/阻塞/死依赖/triage）+ 阈值与 helpers | ❌ |
| └─ `cycle_rules.py` | ✅ 核心 | 循环阻塞 / IN_REVIEW 审批滞留 2 条诊断规则 | ❌ |
| `pipeline/` | ✅ 子包 | Pipeline 模板域（聚合出口见其 `__init__.py`） | - |
| ├─ `instantiator.py` | ✅ 核心 | Pipeline 模板实例化；依赖父任务时继承 `source_chat_id`；`repeat_for_item_skills` 按平台注入 `extra_skill_ids` | ✅ |
| └─ `spec_io.py` | ✅ 核心 | Pipeline frontmatter 解析；`TaskSeed.repeat_for_item_skills` 按 repeat 项注入技能 | ✅ |
| `board_ops.py` | ✅ 核心 | Board CRUD + `project_id/milestone_id` 作用域校验与绑定；`update_board` 在 settings 变更时热刷新运行中 dispatcher（`refresh_board`） | ❌ |
| `task_ops.py` | ✅ 核心 | Task add/update/delete；update 对 `require_approval` 有状态守卫（IN_REVIEW/COMPLETED/FAILED/ARCHIVED 禁改，仅活动状态 TRIAGE/BACKLOG/READY/RUNNING/BLOCKED 可改，避免审批流程开始后语义矛盾） | ❌ |
| `move_orchestrator.py` | ✅ 核心 | move/reclaim/cancel 编排；IN_REVIEW 源/目标守卫（手动 move 绕过审批禁止） | ❌ |
| `review_ops.py` | ✅ 核心 | IN_REVIEW 审批编排：approve→COMPLETED（promote dependents、error 清空）、reject→READY（reason 回写 error、retry_count 重置），优先委托 dispatcher，fallback 走 store 原子 CAS 流转 + 统一 action（task_completed/task_rejected）+ 完成/驳回通知补发（emit_task_rejected）；非 IN_REVIEW 幂等 no-op | ✅ |
| `dependency_ops.py` | ✅ 核心 | 依赖边 CRUD、promote | ❌ |
| `board_summary.py` | ✅ 核心 | `build_board_summary`（含 `stale_running_count`） | ❌ |
| `dispatcher_lifecycle.py` | ✅ 核心 | Dispatcher 启停、boot recovery；注册 task_completed/failed/blocked、task_review_requested 与 task_rejected 通知回调；注册 `BatchDirectoryService.dispatcher_event_hook`（批量目录项目终态检测 → 完成/失败通知） | ❌ |
| `event_publisher.py` | ✅ 核心 | SSE ServerEventBus 发布、`emit_btw_done`、`emit_source_chat_done`（completed/failed/blocked，scheduled block 跳过，共用 `_terminal_status`/`_terminal_result`）、`emit_review_requested`（IN_REVIEW 进入时 pending_review 通知）、`emit_task_rejected`（reject 时 rejected 通知，共用 `_publish_task_notice`）；`_build_background_done_payload` 统一构造 BACKGROUND_TASK_DONE 载荷（BTW/source_chat 路由，thread_id/user_id 空值兜底，含 board_id 供通知点击直达看板 in_review 列） | ❌ |
| `query_ops.py` | ✅ 核心 | Store 只读查询（含 `source_chat_id` / `project_id` 过滤）与 user comment | ❌ |
| `kanban_attach_handler.py` | ✅ 核心 | Worker `kanban_attach` 回调：workspace 路径（相对路径与 `/workspace/...` 抽象路径按 resolve_workspace 基准解析，适配 worktree 隔离）+ HTTPS URL（SSRF guard）→ files vault + task attachment_ids | ✅ |
| `decompose/` | ✅ 子包 | 分解域（聚合出口见其 `__init__.py`） | - |
| ├─ `decomposer.py` | ✅ 核心 | PlatformTaskDecomposer（LiteLLM + WebUI config） | ✅ |
| └─ `orchestrator.py` | ✅ 核心 | TRIAGE→子任务图编排；子任务继承父任务 `source_chat_id` 与 `model_override`，不继承 `require_approval`（审批门禁作用于聚合交付物） | ✅ |
| `specify/` | ✅ 子包 | 规范化域（聚合出口见其 `__init__.py`） | - |
| ├─ `specifier.py` | ✅ 核心 | PlatformTaskSpecifier | ✅ |
| └─ `orchestrator.py` | ✅ 核心 | TRIAGE→spec 编排（`SPECIFY_ALL_MAX_CONCURRENT`、批扫） | ✅ |
| `llm_utils.py` | ✅ 核心 | LLM 辅助工具（specify/decompose 共用） | ✅ |
| `task_attachment_ids.py` | ✅ 核心 | 任务附件 ID 持久化 | ❌ |
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
