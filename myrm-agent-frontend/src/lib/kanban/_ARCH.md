# lib/kanban/

## Overview

Frontend helpers for kanban chat activation: localStorage SSOT for target board id and request payload resolution.

## File Index

| File                                | Role | Description                                                                                                             |
| ----------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------- |
| `kanbanChatBoard.ts`                | Core | `KANBAN_LAST_BOARD_ID_KEY`, read/write, request board id, send guard (stale id clear + `resolveKanbanSendBlockReason*`) |
| `kanbanDecisionFrame.ts`            | Core | 看板任务首屏决策帧要素推导纯函数与责任矩阵任务过滤 (`deriveTaskDecisionFrame`, `filterTasksByResponsibility`) |
| `__tests__/kanbanChatBoard.test.ts` | Test | SSOT, picker visibility, send-block rules                                                                               |
| `__tests__/kanbanDecisionFrame.test.ts` | Test | 决策帧推导单元测试（in_review/blocked/failed/running 状态映射与责任矩阵过滤） |

## Dependencies

- `@/services/kanban` — board list types and API client (Settings + chat config sections)
