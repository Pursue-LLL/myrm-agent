# api/kanban/ 模块架构

## 架构概述

Kanban 看板 REST API：Board/Task CRUD、状态迁移、依赖边、Specify/Decompose TRIAGE 编排、批量操作、诊断与 Pipeline 模板实例化。业务编排见 [services/kanban/_ARCH.md](../../services/kanban/_ARCH.md)；持久化见 [core/kanban/_ARCH.md](../../core/kanban/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | — |
| `http_common.py` | 核心 | 共享 `APIRouter(prefix=/kanban)`、DTO 转换、附件装配 | ✅ |
| `router.py` | 入口 | 聚合 `routes/*` 到 `http_common.router` | ✅ |
| `schemas.py` | 模块 | Kanban API Pydantic 模型（`BoardCreate`/`BoardUpdate` 含全部 9 个 `BoardSettings` 字段，含 `block_recurrence_limit`） | — |
| `pipeline_router.py` | 路由 | Pipeline 模板列表/详情/实例化（独立 router） | ✅ |
| `routes/` | 路由 | 分域端点注册 | [routes/_ARCH.md](routes/_ARCH.md) |

## 挂载（`app/api/router.py`）

- `kanban_router` → `/api/v1` + `http_common` 的 `/kanban` 前缀
- `kanban_pipeline_router` → 同上（`pipeline_router` 自带 `/kanban` 前缀）

## 路由总览（前缀 `/api/v1/kanban`）

| 域 | 端点摘要 |
|----|----------|
| Boards | `GET/POST /boards`（GET 支持 `project_id` 过滤；POST 支持 `project_id` / `milestone_id` 作用域绑定与全部看板设置（含 `block_recurrence_limit`））；`GET/PATCH/DELETE /boards/{id}`（PATCH 支持 settings 部分更新，settings 变更时热刷新运行中 dispatcher）；`GET .../summary`；`GET .../events` |
| Tasks | `GET/POST /boards/{id}/tasks`（GET 可选 `source_chat_id` 按来源会话过滤；POST body 可选 `metadata` 合并入 task.metadata，如 `source_chat_id`）；`GET/PATCH/DELETE /tasks/{id}`；`POST .../move`（IN_REVIEW 进出守卫：手动 move 出入均 409）；`.../approve`（IN_REVIEW→COMPLETED，非 IN_REVIEW 幂等 200）、`.../reject`（IN_REVIEW→READY，reason 必填回写 error + retry_count 重置，非 IN_REVIEW 幂等 200）；`.../promote`、`.../reclaim` |
| Bulk | `POST /boards/{id}/tasks/bulk-action`（move/archive/reassign/reclaim/delete） |
| Meta | runs/events/comments/diagnostics；board/task 依赖边 CRUD |
| Specify | `POST /tasks/{id}/specify`；`.../apply-spec`；`POST /boards/{id}/specify-all` |
| Decompose | `POST /tasks/{id}/decompose`；`.../apply-decompose` |
| Pipeline | `GET /pipelines`；`GET /pipelines/{skill_id}`；`POST /boards/{id}/pipeline/instantiate` |

## 模块依赖

- `app.services.kanban.KanbanService` — 业务编排
- `app.services.kanban.diagnostics` — 任务诊断引擎
- `app.services.kanban.pipeline.instantiator` — Pipeline 确定性实例化
- `myrm_agent_harness.toolkits.kanban.types` — 域类型与状态枚举
