/**
 * [INPUT]
 * @/services/kanban::KanbanBoard (POS: 看板 API 类型)
 *
 * [OUTPUT]
 * KANBAN_LAST_BOARD_ID_KEY, read/write helpers, chat request board resolution, send guard.
 *
 * [POS]
 * Chat ↔ Settings 共享的看板 ID localStorage SSOT；发消息时解析 default_board_id。
 */

import type { KanbanBoard } from '@/services/kanban';

/** SSOT key — shared with Settings KanbanSection. */
export const KANBAN_LAST_BOARD_ID_KEY = 'kanban_last_board_id';

export function readKanbanLastBoardId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(KANBAN_LAST_BOARD_ID_KEY);
    const trimmed = raw?.trim();
    return trimmed || null;
  } catch {
    return null;
  }
}

export function writeKanbanLastBoardId(boardId: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (boardId?.trim()) {
      localStorage.setItem(KANBAN_LAST_BOARD_ID_KEY, boardId.trim());
    } else {
      localStorage.removeItem(KANBAN_LAST_BOARD_ID_KEY);
    }
  } catch {
    /* private mode / quota */
  }
}

export function resolveKanbanChatBoardId(boards: KanbanBoard[]): string | null {
  if (boards.length === 0) return null;
  if (boards.length === 1) return boards[0]!.board_id;

  const saved = readKanbanLastBoardId();
  if (saved && boards.some((b) => b.board_id === saved)) {
    return saved;
  }
  return null;
}

export function shouldShowKanbanBoardPicker(boards: KanbanBoard[]): boolean {
  return boards.length > 1 && resolveKanbanChatBoardId(boards) === null;
}

export function resolveKanbanDefaultBoardIdForRequest(
  enabledBuiltinTools: readonly string[],
): string | undefined {
  if (!enabledBuiltinTools.includes('kanban')) return undefined;
  const id = readKanbanLastBoardId();
  return id ?? undefined;
}

export type KanbanSendBlockReason = 'no_boards' | 'need_board';

/** Sync guard reason from a board list (same rules as KanbanConfigSection picker). */
export function resolveKanbanSendBlockReasonFromBoards(
  boards: KanbanBoard[],
): KanbanSendBlockReason | null {
  if (boards.length === 0) return 'no_boards';
  if (shouldShowKanbanBoardPicker(boards)) return 'need_board';
  return null;
}

/** Block send when kanban is on but no target board can be resolved for the request. */
export async function resolveKanbanSendBlockReason(
  enabledBuiltinTools: readonly string[],
): Promise<KanbanSendBlockReason | null> {
  if (!enabledBuiltinTools.includes('kanban')) return null;
  if (readKanbanLastBoardId()) return null;

  try {
    const { listBoards } = await import('@/services/kanban');
    const { items } = await listBoards();
    return resolveKanbanSendBlockReasonFromBoards(items);
  } catch {
    return null;
  }
}
