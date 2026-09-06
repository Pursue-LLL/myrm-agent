# background-tasks/

## 架构概述

后台活动命令中心：Kanban Agent 任务 + harness 耗时任务（Shell 执行层）+ 跨会话 Goal，统一在 NavBar Popover 展示。用户可见分区标题为「耗时任务 / Long-running tasks」（`backgroundTasks.shellSection`），行内仍显示用户原话 `task.prompt`。

Shell 完成刷新：`useGlobalEvents` 收到 `SYSTEM_NOTIFICATION`（`meta.kind=background_job_finish`）时调用 `notifyBackgroundTasksChangedForShellJobFinish` → Panel/tray 即时对齐（含跨 chat / Tauri tray）。媒体任务经 `taskEventStream` 共享 `/api/v1/tasks/stream`（Chat 任务卡、Panel、tray、离屏 notify 单连接）；离屏完成时 browser/Tauri 通知，Tauri 权限拒则 dock bounce。

## 文件清单

| 文件                                | 地位    | 职责                                                                                                                                                                                                                                                                                    | I/O/P |
| ----------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `BackgroundTasksPanel.tsx`          | ✅ 核心 | NavBar Popover 壳层：轮询、SSE refresh、分区编排；集成多维度动态搜索过滤（支持按 prompt、command、status、task_id、result_preview 全文模糊即时匹配与一键清空）；合并 `/api/v1/tasks` 媒体任务（image/video generate）；`vault_log_ref` 时复用 `EvictedOutputDrawer` 查看完整 spill 日志 | ✅    |
| `BackgroundTaskRow.tsx`             | ✅ 核心 | 单条 Shell/Agent 任务行（progress、running/completed `result_preview`、Cancel `data-testid=background-task-cancel`、Steer、running shell **Send input** → `POST /background-tasks/shell:{job_id}/stdin`、`viewFullLog`「查看完整日志 / View full log」→ Drawer；`navigate` 为跳转会话） | ✅    |
| `MediaTaskRow.tsx`                  | ✅ 核心 | 单条媒体任务行：active（Cancel+进度）/ terminal（完成/失败+错误摘要）；Navigate → `/chat/{chat_id}`                                                                                                                                                                                     | ✅    |
| `ActiveGoalsSection.tsx`            | ✅ 核心 | Active Goals 列表与 pause/resume/cancel                                                                                                                                                                                                                                                 | ✅    |
| `backgroundTasksPanel.constants.ts` | 辅助    | 轮询间隔、状态样式映射与 Goal 类型常量                                                                                                                                                                                                                                                  | ✅    |

## 依赖

- `@/services/background-tasks`、`@/services/backgroundTasksRefresh`、`@/services/mediaTasks`
- `@/hooks/tasks/useMediaBackgroundTasks`、`@/hooks/tasks/useGlobalMediaTaskNotifications`
- `@/lib/api`（fetchWithTimeout）、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
