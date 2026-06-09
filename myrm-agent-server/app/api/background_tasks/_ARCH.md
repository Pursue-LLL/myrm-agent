# api/background_tasks/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

Background tasks API 为前端 `BackgroundTasksPanel` 提供 REST 接口。
任务通过 Kanban 系统持久化存储（系统 Board `__background_tasks__`），
具备重启恢复、僵尸检测、自动重试能力。超时由 Kanban `max_runtime_seconds` 管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Background tasks API — manage /background (/btw /bg) session tasks. | ✅ |
| `router.py` | 路由 | REST API layer for background task management. Reads from Kanban store via ChannelBackgroundTaskHandler. | ✅ |

## 依赖

- `app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler` — 业务逻辑层
- `app.services.kanban::KanbanService` — 持久化存储层
