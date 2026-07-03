# api/background_tasks/

## 架构概述

后台任务 HTTP 层：查询/取消/恢复离线 Agent 任务，以及 **Shell 进程**（harness registry）活动视图。
上级文档：[../_ARCH.md](../_ARCH.md)。

`BackgroundTasksPanel` 通过本路由同时展示：
- **Agent 任务** — Kanban 持久化（`/btw`、子 Agent）
- **Shell 任务** — `BackgroundProcessRegistry` 内存快照（Web 聊天 `run_in_background`）

Shell 任务 ephemeral（服务重启丢失）；自然结束或 cancel 后由 harness AutoUnmount 清理 deferred tool。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Background tasks API — manage /background (/btw /bg) session tasks. | ✅ |
| `router.py` | 路由 | 合并 Kanban + shell registry；`shell:{pid}` cancel 走 harness kill | ✅ |

## 依赖

- `app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler` — Kanban agent 任务
- `app.services.agent.shell_background_tasks` — harness registry 门面
- `app.services.kanban::KanbanService` — Agent 任务持久化
