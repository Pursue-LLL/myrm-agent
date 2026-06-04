# api/kanban/ 模块架构

## 架构概述

Kanban REST API 端点。纯 HTTP 层，参数解析后委托给 KanbanService。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 空模块标记 | ❌ |
| `router.py` | ✅ 核心 | 聚合入口，挂载 `routes/*` 子模块 | ✅ |
| `http_common.py` | ✅ 核心 | 共享 `router`、附件解析、DTO 转换、`get_kanban_service()` | ✅ |
| `routes/boards.py` | ✅ 核心 | 看板 CRUD、summary、events、edges | ✅ |
| `routes/tasks.py` | ✅ 核心 | 任务 CRUD、move、promote、reclaim | ✅ |
| `routes/bulk.py` | ✅ 核心 | 批量操作 bulk-action | ✅ |
| `routes/task_meta.py` | ✅ 核心 | runs、events、comments、diagnostics、dependencies | ✅ |
| `routes/specify.py` | ✅ 核心 | specify / decompose 端点 | ✅ |
| `pipeline_router.py` | ✅ 核心 | Pipeline 模板端点（list / detail / instantiate） | ✅ |
| `schemas.py` | ✅ 核心 | Pydantic 请求/响应模型（含诊断/Pipeline DTO） | ✅ |

## 端点清单

| 方法 | 路径 | 职责 |
|------|------|------|
| GET | `/kanban/boards` | 列出所有看板 |
| POST | `/kanban/boards` | 创建看板（含 specify_max_tokens / auto_specify_on_create） |
| GET | `/kanban/boards/{board_id}` | 获取看板详情 |
| PATCH | `/kanban/boards/{board_id}` | 更新看板（含 specify_* 字段） |
| DELETE | `/kanban/boards/{board_id}` | 删除看板 |
| GET | `/kanban/boards/{board_id}/summary` | 看板统计摘要（含 by_agent 分布、oldest_ready_age） |
| GET | `/kanban/boards/{board_id}/events` | 看板级聚合事件流（kinds/assignee/since_id/since_time/limit 过滤，含 task_title） |
| GET | `/kanban/boards/{board_id}/tasks` | 列出看板任务（含诊断摘要） |
| POST | `/kanban/boards/{board_id}/tasks` | 创建任务（支持 `initial_status=triage` 与 board.auto_specify_on_create 自动触发） |
| GET | `/kanban/tasks/{task_id}` | 获取任务详情 |
| PATCH | `/kanban/tasks/{task_id}` | 更新任务 |
| POST | `/kanban/tasks/{task_id}/move` | 移动任务状态（TRIAGE 出口仅允许 BACKLOG/READY/ARCHIVED；`force=true` 跳过依赖检查强制 promote；依赖未满足时 409 返回 `{code: "deps_unmet", unsatisfied, unmet_parents: [{task_id, title, status}]}` 结构化错误含父任务详情内联） |
| POST | `/kanban/tasks/{task_id}/promote` | 手动 promote BACKLOG→READY（`force=true` 跳过未满足依赖；返回 `unmet_parents` 列表供前端确认对话框使用） |
| POST | `/kanban/tasks/{task_id}/reclaim` | 手动回收 RUNNING 任务：cancel asyncio worker + 关闭 run + 重置 READY + 可选 reassign agent（409 if 非 RUNNING） |
| DELETE | `/kanban/tasks/{task_id}` | 删除任务 |
| GET | `/kanban/tasks/{task_id}/runs` | 列出执行记录 |
| GET | `/kanban/tasks/{task_id}/events` | 列出事件流（支持 `since_id` 增量；含 SPECIFIED/PROMOTED 事件） |
| GET | `/kanban/tasks/{task_id}/dependencies` | 列出上游依赖任务 |
| GET | `/kanban/tasks/{task_id}/dependents` | 列出下游被依赖任务 |
| POST | `/kanban/tasks/{task_id}/dependencies` | 添加依赖关系 |
| POST | `/kanban/tasks/{task_id}/comments` | 添加评论（USER_COMMENT 事件） |
| DELETE | `/kanban/tasks/{task_id}/dependencies/{parent_id}` | 移除依赖关系 |
| GET | `/kanban/boards/{board_id}/edges` | 批量获取看板全部依赖边（供 DAG 图渲染） |
| GET | `/kanban/tasks/{task_id}/diagnostics` | 全量诊断（5 条规则含 dead_dependency / stranded_in_triage） |
| POST | `/kanban/tasks/{task_id}/specify` | 单任务 TRIAGE→spec 重写；`?dry_run=true` 仅预览不持久化 |
| POST | `/kanban/tasks/{task_id}/apply-spec` | 持久化缓存的 dry-run 结果，不调用 LLM；前端 Apply & Promote 使用，避免双倍 token |
| POST | `/kanban/boards/{board_id}/specify-all` | 看板内所有 TRIAGE 任务批量规范化，`asyncio.Semaphore(3)` 限流 |
| POST | `/kanban/tasks/{task_id}/decompose` | 单任务 TRIAGE→子任务图分解预览（dry-run），LLM 返回子任务列表含 assignee 和 parent_indices |
| POST | `/kanban/tasks/{task_id}/apply-decompose` | 持久化分解结果：fanout=true 原子创建子任务+依赖边+DECOMPOSED 事件；fanout=false 降级为 Specify（TRIAGE→READY）+SPECIFIED 事件 |
| GET | `/kanban/pipelines` | 列出可用 Pipeline 模板（category=pipeline 的 prebuilt skills） |
| GET | `/kanban/pipelines/{skill_id}` | 获取 Pipeline 模板详情（含 discovery_questions、role_templates、task_graph_seed） |
| POST | `/kanban/boards/{board_id}/pipeline/instantiate` | 实例化 Pipeline 模板为任务 DAG（确定性字符串替换 + 批量创建 tasks + edges） |
| POST | `/kanban/boards/{board_id}/tasks/bulk-action` | 批量操作（move/archive/reassign/reclaim/delete），最多 100 个任务，delete 需 confirm=true，move 支持 params.force 强制跳过依赖，reclaim 支持 params.reason/new_agent_id |

### 响应增强

`GET /boards/{board_id}/tasks` 返回的 TaskResponse 包含批量预取的卡片统计字段：
- `dep_count`：上游依赖任务数
- `children_total`：下游子任务总数
- `children_done`：已完成的下游子任务数
- `comment_count`：用户评论数
- `attachment_ids`：附件文件 ID 列表（批量加载，`_batch_load_attachment_ids` 避免 N+1；`max_length=10` 防 token 膨胀）
- `attachments`：附件元数据列表（`AttachmentInfo`：file_id, filename, content_type, url），由 `_resolve_attachments` 从 file_id 批量解析
- `diagnostics_summary`：诊断摘要（count + max_severity），仅运行快速规则（stranded_in_ready / repeated_failures / stuck_in_blocked / stranded_in_triage）

### 诊断策略

- **卡片级（list_tasks）**：仅运行 O(1) 快速规则，返回 `diagnostics_summary`（count + max_severity）
- **抽屉级（/diagnostics）**：运行全部 5 条规则（含需要查询父任务状态的 dead_dependency），返回完整诊断列表含 actions

## 依赖关系

### 内部依赖
- `app/services/kanban/`：KanbanService 业务编排
- `app/services/kanban/diagnostics`：诊断规则与引擎
- `myrm_agent_harness/toolkits/kanban/types`：域类型
- `myrm_agent_harness/toolkits/kanban/diagnostics`：诊断框架 DTO/Protocol/Engine

### 被依赖方
- `app/api/router.py`：主路由注册
