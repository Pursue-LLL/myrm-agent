# api/tasks/

## 架构概述

通用异步任务队列 HTTP 层 — 查询 harness `SQLiteTaskStore` 中的任务状态，经 SSE 推送到前端。
上级文档：[../_ARCH.md](../_ARCH.md)。业务 worker：[../../tasks/_ARCH.md](../../tasks/_ARCH.md)。

## 端点与消费

| 路由 | 用途 | 前端消费 |
|------|------|----------|
| `GET /api/v1/tasks` | 列表/过滤（`ids` 批量过滤，`detail=true` 返回 payload/result） | 任务历史 + 订阅断线回退 |
| `GET /api/v1/tasks/{id}` | 单任务状态 | ImageTaskCard 初始加载 |
| `GET /api/v1/tasks/stream` | SSE 实时更新 | `useTasksSubscription` |
| `POST /api/v1/tasks/{id}/retry` | 重试失败任务（错误返回结构化 `detail={code,message,recoverable}`），仅当任务仍为 `failed` 时以 compare-and-set 重置旧输出与生命周期字段并立即广播 `pending` 事件 | ImageTaskCard / VideoTaskCard 重试按钮 |
| `POST /api/v1/tasks/{id}/cancel` | 取消未结束的任务：仅当仍为 `pending/queued/running` 时以 compare-and-set 写 `cancelled`（已结束返回 `TASK_ALREADY_COMPLETED`），再由 worker 中止在途执行并广播 `cancelled` 事件 | ImageTaskCard / VideoTaskCard 取消按钮 |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Task API module. | ✅ |
| `router.py` | 路由 | Task management API routes. | ✅ |
| `deps.py` | 辅助 | `get_task_store` / `get_task_worker` FastAPI 依赖（worker 未启动时为 None） | ✅ |
| `timeline_router.py` | 路由 | 任务执行时序树与瀑布流快照查询、即时插嘴打断端点（`/tasks/{task_id}/timeline`, `/tasks/{task_id}/interrupt`） | ✅ |
| `test_fixtures.py` | 测试 | local-only Chrome E2E seed（`POST /tasks/test/seed-media-fixture`；`mode=failed` / `succeeded` / `running`） | ✅ |

## Key Dependencies

- `app.lifecycle.task_worker.get_task_store` / `get_task_worker` — harness `SQLiteTaskStore` 与运行中的 `TaskWorker`
- `app.tasks.events` — SSE 事件总线
