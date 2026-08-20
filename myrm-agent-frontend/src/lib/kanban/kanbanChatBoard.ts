/**
 * [INPUT]
 * @/services/kanban::KanbanBoard (POS: 看板 API 类型)
 *
 * [OUTPUT]
 * KANBAN_LAST_BOARD_ID_KEY, read/write helpers, chat request board resolution, send guard,
 * buildKanbanBoardDeepLink.
 *
 * [POS]
 * Chat ↔ Settings 共享的看板 ID localStorage SSOT；发消息时解析 default_board_id。
 */

import type { KanbanBoard } from '@/services/kanban';

/** SSOT key — shared with Settings KanbanSection. */
export const KANBAN_LAST_BOARD_ID_KEY = 'kanban_last_board_id';

function normalizeKanbanProjectScope(projectId: string | null | undefined): string | null {
  const trimmed = projectId?.trim();
  return trimmed ? trimmed : null;
}

function resolveKanbanStorageKey(projectId: string | null | undefined): string {
  const scope = normalizeKanbanProjectScope(projectId);
  if (!scope) {
    return KANBAN_LAST_BOARD_ID_KEY;
  }
  return `${KANBAN_LAST_BOARD_ID_KEY}:${scope}`;
}

export function readKanbanLastBoardId(projectId?: string | null): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const scopedKey = resolveKanbanStorageKey(projectId);
    const scopedValue = localStorage.getItem(scopedKey)?.trim();
    if (scopedValue) {
      return scopedValue;
    }
    return null;
  } catch {
    return null;
  }
}

export function writeKanbanLastBoardId(boardId: string | null, projectId?: string | null): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const key = resolveKanbanStorageKey(projectId);
    if (boardId?.trim()) {
      localStorage.setItem(key, boardId.trim());
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    /* private mode / quota */
  }
}

export function resolveKanbanChatBoardId(boards: KanbanBoard[], projectId?: string | null): string | null {
  if (boards.length === 0) {
    return null;
  }
  if (boards.length === 1) {
    return boards[0]!.board_id;
  }

  const saved = readKanbanLastBoardId(projectId);
  if (saved && boards.some((b) => b.board_id === saved)) {
    return saved;
  }
  return null;
}

export function shouldShowKanbanBoardPicker(boards: KanbanBoard[], projectId?: string | null): boolean {
  return boards.length > 1 && resolveKanbanChatBoardId(boards, projectId) === null;
}

export function resolveKanbanDefaultBoardIdForRequest(
  enabledBuiltinTools: readonly string[],
  projectId?: string | null,
): string | undefined {
  if (!enabledBuiltinTools.includes('kanban')) {
    return undefined;
  }
  const id = readKanbanLastBoardId(projectId);
  return id ?? undefined;
}

/** Deep link into Settings Kanban board view with optional session filter. */
export function buildKanbanBoardDeepLink(opts: { sourceChatId: string; boardId: string }): string {
  const params = new URLSearchParams({
    source_chat: opts.sourceChatId.trim(),
    board_id: opts.boardId.trim(),
  });
  return `/settings/kanban?${params.toString()}`;
}

export type KanbanSendBlockReason = 'no_boards' | 'need_board';

/** Sync guard reason from a board list (same rules as KanbanConfigSection picker). */
export function resolveKanbanSendBlockReasonFromBoards(
  boards: KanbanBoard[],
  projectId?: string | null,
): KanbanSendBlockReason | null {
  if (boards.length === 0) {
    return 'no_boards';
  }

  const saved = readKanbanLastBoardId(projectId);
  if (saved && !boards.some((b) => b.board_id === saved)) {
    writeKanbanLastBoardId(null, projectId);
  }

  if (shouldShowKanbanBoardPicker(boards, projectId)) {
    return 'need_board';
  }
  return null;
}

/** Block send when kanban is on but no target board can be resolved for the request. */
export async function resolveKanbanSendBlockReason(
  enabledBuiltinTools: readonly string[],
  projectId?: string | null,
): Promise<KanbanSendBlockReason | null> {
  if (!enabledBuiltinTools.includes('kanban')) {
    return null;
  }

  try {
    const { listBoards } = await import('@/services/kanban');
    const { items } = await listBoards({ projectId: normalizeKanbanProjectScope(projectId) });
    return resolveKanbanSendBlockReasonFromBoards(items, projectId);
  } catch {
    return null;
  }
}
