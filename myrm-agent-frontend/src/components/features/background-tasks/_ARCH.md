# background-tasks/

## 架构概述

后台任务命令中心：列表展示、进度轮询、取消与方向调整操作。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BackgroundTasksPanel.tsx` | ✅ 核心 | 后台任务面板组件，展示所有后台任务状态（running/completed/failed/timed_out/cancelled），支持任务取消和方向调整（steer）。运行中任务快速轮询（3s），空闲时降频（30s）。timed_out 任务以琥珀色时钟图标区分展示，与 failed 状态明确区分 | ✅ |

## 依赖

- `@/store/*`、`@/services/background-tasks`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
