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
| `query_ops.py` | ✅ 核心 | Store 只读查询与 user comment | ❌ |
| `service_types.py` | ✅ 核心 | DTO/异常/常量 | ❌ |
| `event_publisher.py` | ✅ 核心 | SSE EventBus 发布、`emit_btw_done` | ❌ |
| `board_ops.py` | ✅ 核心 | Board CRUD | ❌ |
| `task_ops.py` | ✅ 核心 | Task add/update/delete | ❌ |
| `move_orchestrator.py` | ✅ 核心 | move/reclaim/cancel 编排 | ❌ |
| `dependency_ops.py` | ✅ 核心 | 依赖边 CRUD、promote | ❌ |
| `board_summary.py` | ✅ 核心 | `build_board_summary` | ❌ |
| `dispatcher_lifecycle.py` | ✅ 核心 | Dispatcher 启停、boot recovery | ❌ |
| `task_runner.py` | ✅ 核心 | KanbanTaskRunner 编排入口 | ✅ |
| `task_runner_stream.py` | ✅ 核心 | Stream 累积、附件、multimodal query | ❌ |
| `task_runner_worktree.py` | ✅ 核心 | Git worktree 隔离 | ❌ |
| `task_runner_profile.py` | ✅ 核心 | Agent profile 解析 | ❌ |
| `diagnostics.py` | ✅ 核心 | 诊断引擎工厂、摘要 | ✅ |
| `diagnostic_rules.py` | ✅ 核心 | 6 条诊断规则 | ❌ |
| `specifier.py` | ✅ 核心 | PlatformTaskSpecifier | ✅ |
| `specify_orchestrator.py` | ✅ 核心 | TRIAGE→spec 编排 | ✅ |
| `llm_utils.py` | ✅ 核心 | LLM 辅助工具（specifier/decomposer 共用） | ✅ |
| `decomposer.py` | ✅ 核心 | PlatformTaskDecomposer | ✅ |
| `decompose_orchestrator.py` | ✅ 核心 | TRIAGE→子任务图编排 | ✅ |
| `pipeline_spec_io.py` | ✅ 核心 | Pipeline frontmatter 解析 | ✅ |
| `pipeline_instantiator.py` | ✅ 核心 | Pipeline 模板实例化 | ✅ |
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
