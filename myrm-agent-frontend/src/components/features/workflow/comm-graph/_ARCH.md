# 多智能体协同通讯图套件架构设计 (_ARCH.md)

## 1. 业务愿景与核心痛点
对标 `traycer` PR #1767 生产级前端交互实践，直击多智能体协同通讯图（Comm-Graph）的经典交互硬伤：
- **痛点 1（死锁卡死错觉）**：多智能体任务刚启动、尚未产生消息事件时（`events.length === 0`），传统设计展现一条空白轨道，旁边有一个禁用的 Play 按钮，却亮起绿色的“Live 实时”徽标，极易误导用户认为系统假死或死锁；
- **痛点 2（单向门丢失审阅心流）**：用户在回看审阅历史第 N 步时，一旦点击“Live”切入最新实时状态，系统就把原先的浏览游标直接丢弃（变成单向门）。用户若想回到第 N 步，必须自行在几十条事件中重新肉眼查找。

## 2. 解决方案与状态机设计
```
                     [ 任务启动 events.length === 0 ]
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │   CommGraphEmptyStateCard    │
                     │   - 隐藏误导性 Live 高亮绿灯 │
                     │   - 明确展示初始化流水线占位 │
                     └──────────────┬───────────────┘
                                    │ 事件到达 / events.length > 0
                                    ▼
                     ┌──────────────────────────────┐
                     │   CommGraphTimelineTrack     │
                     └──────────────┬───────────────┘
                                    │
           ┌────────────────────────┴────────────────────────┐
           ▼                                                 ▼
[用户审阅历史事件 selectedEventId]               [用户点击 Live 切换到实时最新]
- isLive = false                                - isLive = true
- 记录当前位置: returnCursorId = selectedId     - selectedEventId = latestEventId
           │                                                 │
           └──────────────── 用户再次点击 Live ───────────────┘
                                    │
                                    ▼
             [恢复原先审阅位置: selectedEventId = returnCursorId]
```

## 3. 文件组织与模块职责
- `commGraphTypes.ts`：协同事件模型（`AgentCommEvent`）、时间轴状态机与 Store 接口；
- `useCommGraphStore.ts`：Zustand 集中式状态管理，承载双向游标记忆（`returnCursorId`）存取逻辑与空状态受控；
- `CommGraphEmptyStateCard.tsx`：静音空状态展示卡片，隐藏误导性 Live 徽标，提供礼貌的状态告知（`role="status"` 与 `aria-live="polite"`）；
- `CommGraphTimelineTrack.tsx`：横向步骤轨道、多智能体调用上下文、载荷摘要与 Live 双向切换按钮；
- `CommGraphMultiSurfaceCard.tsx`：生产级主卡片，提供快捷仿真事件注入与状态重置；
- `index.ts`：统一模块导出。
