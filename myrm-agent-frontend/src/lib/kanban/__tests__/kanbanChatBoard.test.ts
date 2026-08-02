import { describe, expect, it, beforeEach, afterEach } from 'vitest';

import {
  KANBAN_LAST_BOARD_ID_KEY,
  readKanbanLastBoardId,
  resolveKanbanChatBoardId,
  resolveKanbanDefaultBoardIdForRequest,
  resolveKanbanSendBlockReasonFromBoards,
  shouldShowKanbanBoardPicker,
  buildKanbanBoardDeepLink,
  writeKanbanLastBoardId,
} from '@/lib/kanban/kanbanChatBoard';
import type { KanbanBoard } from '@/services/kanban';

function board(id: string, name: string): KanbanBoard {
  return {
    board_id: id,
    name,
    description: '',
    settings: { max_concurrent_tasks: 1, heartbeat_interval_seconds: 30, zombie_timeout_seconds: 300, max_retries_per_task: 3, auto_block_after_consecutive_failures: 3, specify_max_tokens: 4096, auto_specify_on_create: false },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

describe('kanbanChatBoard', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('reads and writes last board id', () => {
    expect(readKanbanLastBoardId()).toBeNull();
    writeKanbanLastBoardId('board-a');
    expect(localStorage.getItem(KANBAN_LAST_BOARD_ID_KEY)).toBe('board-a');
    expect(readKanbanLastBoardId()).toBe('board-a');
    writeKanbanLastBoardId(null);
    expect(readKanbanLastBoardId()).toBeNull();
  });

  it('stores board selection per project scope', () => {
    writeKanbanLastBoardId('project-board', 'proj-1');
    writeKanbanLastBoardId('global-board');
    expect(readKanbanLastBoardId('proj-1')).toBe('project-board');
    expect(readKanbanLastBoardId('proj-2')).toBeNull();
    expect(readKanbanLastBoardId()).toBe('global-board');
  });

  it('auto-picks sole board', () => {
    const boards = [board('only', 'Only')];
    expect(resolveKanbanChatBoardId(boards, 'proj-a')).toBe('only');
    expect(shouldShowKanbanBoardPicker(boards, 'proj-a')).toBe(false);
  });

  it('uses saved board when valid among many', () => {
    writeKanbanLastBoardId('b2', 'proj-a');
    const boards = [board('b1', 'One'), board('b2', 'Two')];
    expect(resolveKanbanChatBoardId(boards, 'proj-a')).toBe('b2');
    expect(shouldShowKanbanBoardPicker(boards, 'proj-a')).toBe(false);
  });

  it('requires picker when multiple boards and no valid saved id', () => {
    const boards = [board('b1', 'One'), board('b2', 'Two')];
    expect(resolveKanbanChatBoardId(boards, 'proj-a')).toBeNull();
    expect(shouldShowKanbanBoardPicker(boards, 'proj-a')).toBe(true);
  });

  it('includes board id in request only when kanban enabled', () => {
    writeKanbanLastBoardId('board-x', 'proj-a');
    expect(resolveKanbanDefaultBoardIdForRequest(['web_search'])).toBeUndefined();
    expect(resolveKanbanDefaultBoardIdForRequest(['kanban'], 'proj-a')).toBe('board-x');
  });

  it('blocks send when no boards exist', () => {
    expect(resolveKanbanSendBlockReasonFromBoards([])).toBe('no_boards');
  });

  it('blocks send when multiple boards and no selection', () => {
    const boards = [board('b1', 'One'), board('b2', 'Two')];
    expect(resolveKanbanSendBlockReasonFromBoards(boards, 'proj-a')).toBe('need_board');
  });

  it('clears stale saved id and blocks when board was deleted', () => {
    writeKanbanLastBoardId('deleted-board', 'proj-a');
    const boards = [board('b1', 'One'), board('b2', 'Two')];
    expect(resolveKanbanSendBlockReasonFromBoards(boards, 'proj-a')).toBe('need_board');
    expect(readKanbanLastBoardId('proj-a')).toBeNull();
  });

  it('allows send when sole board without saved id', () => {
    expect(resolveKanbanSendBlockReasonFromBoards([board('only', 'Only')], 'proj-a')).toBeNull();
  });

  it('builds board deep link with source chat and board id', () => {
    expect(
      buildKanbanBoardDeepLink({ sourceChatId: 'chat-1', boardId: 'board-9' }),
    ).toBe('/settings/kanban?source_chat=chat-1&board_id=board-9');
  });
});
