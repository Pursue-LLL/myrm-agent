# background-tasks/

## 架构概述

后台任务与全局 Goal 命令中心：列表展示、进度轮询、取消、方向调整与跨会话 Goal 追踪操作。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BackgroundTasksPanel.tsx` | ✅ 核心 | NavBar Popover 面板。上半部分展示跨会话活跃 Goal（状态、tokens 消耗、暂停/恢复/取消/会话导航）；下半部分展示后台任务状态（running/completed/failed/timed_out/cancelled）及取消和方向调整（steer）。运行中快速轮询（3s），空闲时降频（30s），SSE 事件驱动实时刷新 | ✅ |

## 依赖

- `@/lib/api`（fetchWithTimeout）、`@/services/background-tasks`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
