# api/background_tasks/

## 架构概述

后台任务 HTTP 层：查询/取消/恢复离线 Agent 任务，以及 **Shell 进程**（harness registry + BSDL Store）活动视图。
上级文档：[../_ARCH.md](../_ARCH.md)。

`BackgroundTasksPanel` 通过本路由同时展示：
- **Agent 任务** — Kanban 持久化（`/btw`、子 Agent）
- **耗时任务（Shell 执行层）** — 内存 registry 与 Volume 上 `BackgroundJobStore` 合并列表（Web 聊天 `run_in_background`）；GUI 分区标题见 `backgroundTasks.shellSection`

耗时任务：`task_id=shell:{job_id}`（32 位 hex）；服务重启后 Store 中 running 行 reconcile 为 **orphaned**；`registry_ephemeral=false` 当 Store 已 configure。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Background tasks API — manage /background (/btw /bg) session tasks. | ✅ |
| `router.py` | 路由 | 合并 Kanban + shell；暴露 `job_id` / `vault_log_ref`；shell cancel 走 harness kill；`POST /{task_id}/stdin` GUI 手动 stdin | ✅ |
| `test_fixtures.py` | 测试 | local-only Chrome E2E seed（`POST /background-tasks/test/seed-shell-fixture`；`mode=running` / **`running_stdin`** / failed / success / completed_with_vault） | ✅ |

## 依赖

- `app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler` — Kanban agent 任务
- `app.services.agent.shell_background_tasks` — registry + Store 门面
- `app.services.kanban::KanbanService` — Agent 任务持久化
