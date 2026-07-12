# background-tasks/

## 架构概述

后台活动命令中心：Kanban Agent 任务 + harness Shell 任务 + 跨会话 Goal，统一在 NavBar Popover 展示。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BackgroundTasksPanel.tsx` | ✅ 核心 | NavBar Popover 壳层：轮询、SSE refresh、分区编排 | ✅ |
| `BackgroundTaskRow.tsx` | ✅ 核心 | 单条 Shell/Agent 任务行（progress、Cancel、Steer） | ✅ |
| `ActiveGoalsSection.tsx` | ✅ 核心 | Active Goals 列表与 pause/resume/cancel | ✅ |
| `backgroundTasksPanel.constants.ts` | 辅助 | 轮询间隔、状态样式映射与 Goal 类型常量 | ✅ |

## 依赖

- `@/services/background-tasks`、`@/services/backgroundTasksRefresh`
- `@/lib/api`（fetchWithTimeout）、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
