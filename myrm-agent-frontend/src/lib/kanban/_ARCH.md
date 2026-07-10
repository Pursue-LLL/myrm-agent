# lib/kanban/

## Overview

Frontend helpers for kanban chat activation: localStorage SSOT for target board id and request payload resolution.

## File Index

| File | Role | Description |
|------|------|-------------|
| `kanbanChatBoard.ts` | Core | `KANBAN_LAST_BOARD_ID_KEY`, read/write, request board id, send guard (`resolveKanbanSendBlockReason*`) |
| `__tests__/kanbanChatBoard.test.ts` | Test | SSOT, picker visibility, send-block rules |

## Dependencies

- `@/services/kanban` — board list types and API client (Settings + chat config sections)
