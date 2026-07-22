# api/kanban/routes/ 模块架构

## 架构概述

Kanban HTTP 端点分域注册模块，共享 [../http_common.py](../http_common.py) 的 `router`（`/kanban` 前缀）。上级：[../_ARCH.md](../_ARCH.md)。

## 模块依赖

- `app.api.kanban.http_common`：共享 router、DTO 转换与附件解析装配
- `app.services.kanban`：Task/Board/Bulk/Specify 等业务编排
- `app.services.kanban.task_attachment_ids`：Task 附件 ID 读写持久化

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 触发子模块路由注册 | — |
| `boards.py` | 路由 | Board CRUD、summary、board 级 events | ✅ |
| `tasks.py` | 路由 | Task CRUD、move、promote、reclaim | ✅ |
| `bulk.py` | 路由 | `bulk-action`：move/archive/reassign/reclaim/delete | ✅ |
| `task_meta.py` | 路由 | runs、events、comments、diagnostics、依赖边 | ✅ |
| `specify.py` | 路由 | specify/apply-spec/specify-all、decompose/apply-decompose | ✅ |

## 端点明细（`/api/v1/kanban`）

### `boards.py`

| 方法 | 路径 |
|------|------|
| GET/POST | `/boards` |
| GET/PATCH/DELETE | `/boards/{board_id}` |
| GET | `/boards/{board_id}/summary` |
| GET | `/boards/{board_id}/events` |

### `tasks.py`

| 方法 | 路径 |
|------|------|
| GET/POST | `/boards/{board_id}/tasks` | GET 支持 `status_filter`、`agent_id`、`source_chat_id` query；POST body 可选 `metadata`（如 `source_chat_id`） |
| GET/PATCH/DELETE | `/tasks/{task_id}` |
| POST | `/tasks/{task_id}/move` |
| POST | `/tasks/{task_id}/promote` |
| POST | `/tasks/{task_id}/reclaim` |

### `bulk.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/boards/{board_id}/tasks/bulk-action` | `action` ∈ move/archive/reassign/reclaim/delete；delete 需 `confirm=true` |

### `task_meta.py`

| 方法 | 路径 |
|------|------|
| GET | `/tasks/{task_id}/runs` |
| GET | `/tasks/{task_id}/events` |
| POST | `/tasks/{task_id}/comments` |
| GET | `/tasks/{task_id}/diagnostics` |
| GET | `/boards/{board_id}/edges` |
| GET | `/tasks/{task_id}/dependencies` |
| GET | `/tasks/{task_id}/dependents` |
| POST | `/tasks/{task_id}/dependencies` |
| DELETE | `/tasks/{task_id}/dependencies/{parent_task_id}` |

### `specify.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/{task_id}/specify` | `dry_run` 默认 true；false 时持久化并提升 TRIAGE |
| POST | `/tasks/{task_id}/apply-spec` | 持久化预览 spec，避免 LLM 双调用 |
| POST | `/boards/{board_id}/specify-all` | 并发扫描 board 内全部 TRIAGE |
| POST | `/tasks/{task_id}/decompose` | 分解预览（始终 dry-run） |
| POST | `/tasks/{task_id}/apply-decompose` | `fanout=true` 创建子任务图；`false` 降级为 Specify |
