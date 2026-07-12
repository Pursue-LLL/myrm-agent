# chat-window/goals/

对话内 Goal DAG 控制面 UI；状态在 `store/chat/goals/`。

| 文件 | 职责 |
|------|------|
| `GoalStatusCard.tsx` | 活跃 goal 状态卡（`GoalState` 类型 SSOT） |
| `GoalControlPlane.tsx` | 控制面布局 |
| `GoalQueueSection.tsx` / `GoalPlanStepsList.tsx` | 队列与计划步骤 |
| `useGoalPlanSync.ts` | Plan 与 store 同步 |
| `goal-icons.tsx` | Goal 状态图标 |
