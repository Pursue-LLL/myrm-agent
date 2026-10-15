# lib/kanban/

## Overview

Frontend helpers for kanban chat activation: localStorage SSOT for target board id and request payload resolution.

## File Index

| File                                    | Role | Description                                                                                                             |
| --------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------- |
| `kanbanChatBoard.ts`                    | Core | `KANBAN_LAST_BOARD_ID_KEY`, read/write, request board id, send guard (stale id clear + `resolveKanbanSendBlockReason*`) |
| `kanbanDecisionFrame.ts`                | Core | 看板任务首屏决策帧要素推导纯函数与责任矩阵任务过滤 (`deriveTaskDecisionFrame`, `filterTasksByResponsibility`)           |
| `kanbanBlockedReason.ts`                | Core | 阻塞原因的界面语言文案 (`blockedReasonText`，整句取自 shared/config/kanban_blocked_reasons.json，未知原因原样返回)      |
| `__tests__/kanbanChatBoard.test.ts`     | Test | SSOT, picker visibility, send-block rules                                                                               |
| `__tests__/kanbanBlockedReason.test.ts` | Test | 已知原因译成界面语言、未知原因原样、继承属性名不被当成已知原因                                                          |
| `__tests__/kanbanDecisionFrame.test.ts` | Test | 决策帧推导单元测试（in_review/blocked/failed/running 状态映射与责任矩阵过滤）                                           |

## Dependencies

- `@/services/kanban` — board list types and API client (Settings + chat config sections)
