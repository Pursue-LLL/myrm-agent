# services/batch_directory/

## 架构概述

批量目录并行 Prompt 编排业务服务：**同一 prompt × N 目标目录**并行执行。执行完全委托 Kanban 调度器/运行器——每个目标目录生成一个 Kanban 任务（`workspace_path` 指向该目录，metadata 标记 `batch_project_id`）；本服务只负责批次级编排：批量建板/建任务、聚合统计、终态检测通知、取消。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `BatchDirectoryService` 与 `fetch_project_task_models` | — |
| `service.py` | 核心 | 批次编排：`create_project`（建板+扇出任务）、`list_projects`/`get_project`（聚合）、`cancel_project`、`delete_project`、`dispatcher_event_hook`（Kanban 事件终态检测 → `maybe_finalize` → SystemNotification） | ✅ |
| `_helpers.py` | 辅助 | 序列化/查询/路径校验助手：`_project_to_dict`、`_aggregate_statuses`、`_resolve_directory`、`fetch_project_task_models`、`_send_completion_notification`（从 service.py 拆出以维持 400 行预算） | ✅ |

## 领域职责

- **单一事实来源**：任务真值在 `kanban_tasks`，本表只存批次元数据 + 运行聚合；`list_projects`/`get_project` 实时从任务表聚合刷新计数。
- **批板语义**：未指定 `board_id` 时自动创建专用 board（并发上限 = 批次 `concurrency`，`require_approval` 透传）。
- **终态检测**：通过 `dispatcher_event_hook` 监听 Kanban 任务终态事件（task_completed/task_failed/task_blocked/task_archived/task_cancelled），全部终态时置 `status` 并发送 SystemNotification（完成/失败含失败目录清单）。
- **artifact glob 校验**：`artifact_patterns` 随任务 metadata 下发，任务运行后校验产物 glob 匹配结果写入任务结果摘要。

## 内部依赖

- `app.database.models.batch_directory.BatchDirectoryProjectModel` — 批次元数据 ORM
- `app.services.kanban.KanbanService` — `add_task`/`move_task`/`create_board`
- `app.services.infra.system_notification.SystemNotificationService` — 完成/失败通知
- `app.platform_utils.workspace_root.get_workspace_root` + `app.security.path_safety.is_dangerous_path` — 目录安全校验
- `app.database.connection.get_session` — async session
