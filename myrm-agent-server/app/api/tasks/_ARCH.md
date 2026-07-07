# api/tasks/

## 架构概述

通用异步任务队列 HTTP 层 — 查询 harness `SQLiteTaskStore` 中的任务状态，经 SSE 推送到前端。
上级文档：[../_ARCH.md](../_ARCH.md)。业务 worker：[../../tasks/_ARCH.md](../../tasks/_ARCH.md)。

## 端点与消费

| 路由 | 用途 | 前端消费 |
|------|------|----------|
| `GET /api/v1/tasks` | 列表/过滤 | 任务历史 |
| `GET /api/v1/tasks/{id}` | 单任务状态 | ImageTaskCard 初始加载 |
| `GET /api/v1/tasks/stream` | SSE 实时更新 | `useTasksSubscription` |
| `POST /api/v1/tasks/{id}/retry` | 重试失败任务 | ImageTaskCard 重试按钮 |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Task API module. | ✅ |
| `router.py` | 路由 | Task management API routes. | ✅ |

## Key Dependencies

- `app.lifecycle.task_worker.get_task_store` — harness `SQLiteTaskStore`
- `app.tasks.events` — SSE 事件总线
