# store/tasks/ 模块架构

## 架构概述

通用后台任务 Map 状态（`task_id` → `Task`）。与 `hooks/tasks/` WebSocket 订阅配合；区别于 `useCommandStore` 的 Slash 命令中心。

## 文件清单

| 文件 | 职责 |
|------|------|
| `taskStore.ts` | `useTaskStore`：增删改查、fetch/cancel/retry |
| `types.ts` | `Task` 与任务状态枚举 |

## 依赖

- `@/lib/api` — `apiRequest`
- `hooks/tasks/` — 实时推送写入 store

## 约束

- 新后台任务域优先复用本 store，避免平行 `Map` 实现
