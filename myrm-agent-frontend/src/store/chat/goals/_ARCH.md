# store/chat/goals/ 模块架构

## 架构概述

对话内 Goal DAG 与 Plan 步骤状态。与 `components/features/chat-window/goals/` UI 配对；REST 经 `fetchWithTimeout` 直调 `/goals/*`。

## 文件清单

| 文件              | 职责                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `useGoalStore.ts` | 活跃 goal、队列、git 分支、预算/目标更新；`refreshActiveGoal` 供 bg finish / goal_needs_review SSE 同步 Card |
| `usePlanStore.ts` | Plan 步骤树、加载与步骤状态 PATCH                                                                            |
| `__tests__/`      | goal/plan store 回归                                                                                         |

## 依赖

- `@/components/features/chat-window/goals/GoalStatusCard` — `GoalState` 类型 SSOT
- `@/lib/api` — `fetchWithTimeout`

## 约束

- Goal UI 类型定义留在 feature 组件；store 仅引用，不重复声明
- `useGoalStore` 只描述打开的那个聊天：`chatId` 是槽位所属的聊天，`bindChat(chatId)` 在换聊天时清空 `activeGoal` / `gitBranch` / `queuedGoals`（同一聊天重复绑定不动）。所有写入都带发起它的聊天 id，在 `set` 内与当前 `chatId` 比对，已不是打开的聊天则丢弃，所以慢响应与后台通知不会把别的聊天的目标写进当前聊天；SSE 无法确定聊天时传空 id，视为属于当前聊天。绑定与首次加载由 `chat-window/goals/useGoalSync` 完成（`GoalStatusCard` 与移动端 `MobileStatusBoard` 各自挂载）
- 目标文案被服务端风控拦下（HTTP 400 `risk_held`）时，`updateObjective` 抛 `RiskHeldRefusalError`，提示已由 `services/riskHeldToast.ts` 展示一次，调用方用 `isRiskHeldError` 判断后跳过自己的失败提示
