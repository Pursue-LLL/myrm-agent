# background-tasks/

## 架构概述

后台活动命令中心：Kanban Agent 任务 + harness Shell 任务 + 跨会话 Goal，统一在 NavBar Popover 展示。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BackgroundTasksPanel.tsx` | ✅ 核心 | NavBar Popover。分区：**Goals** → **Shell 任务**（`run_in_background`）→ **Agent 任务**（Kanban `/btw`）。Shell 行支持 progress 条、跳转来源 chat、Cancel；Agent 行支持 Cancel + Steer。Trigger 带 i18n Tooltip + running 角标。`subscribeBackgroundTasksChanged` 在 SSE 后台事件时即时 refresh；打开时 3s 轮询，关闭时 30s 降频 | ✅ |

## 依赖

- `@/services/background-tasks`、`@/services/backgroundTasksRefresh`
- `@/lib/api`（fetchWithTimeout）、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
