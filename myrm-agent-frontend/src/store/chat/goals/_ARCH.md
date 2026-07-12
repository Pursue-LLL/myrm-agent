# store/chat/goals/ 模块架构

## 架构概述

对话内 Goal DAG 与 Plan 步骤状态。与 `components/features/chat-window/goals/` UI 配对；REST 经 `fetchWithTimeout` 直调 `/goals/*`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useGoalStore.ts` | 活跃 goal、队列、git 分支、预算/目标更新 |
| `usePlanStore.ts` | Plan 步骤树、加载与步骤状态 PATCH |
| `__tests__/` | goal/plan store 回归 |

## 依赖

- `@/components/features/chat-window/goals/GoalStatusCard` — `GoalState` 类型 SSOT
- `@/lib/api` — `fetchWithTimeout`

## 约束

- Goal UI 类型定义留在 feature 组件；store 仅引用，不重复声明
