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
    const boards = [{ board_id: 'only', name: 'Only' }];
    expect(resolveKanbanChatBoardId(boards, 'proj-a')).toBe('only');
    expect(shouldShowKanbanBoardPicker(boards, 'proj-a')).toBe(false);
  });

  it('uses saved board when valid among many', () => {
    writeKanbanLastBoardId('b2', 'proj-a');
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanChatBoardId(boards, 'proj-a')).toBe('b2');
    expect(shouldShowKanbanBoardPicker(boards, 'proj-a')).toBe(false);
  });

  it('requires picker when multiple boards and no valid saved id', () => {
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
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
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanSendBlockReasonFromBoards(boards, 'proj-a')).toBe('need_board');
  });

  it('clears stale saved id and blocks when board was deleted', () => {
    writeKanbanLastBoardId('deleted-board', 'proj-a');
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanSendBlockReasonFromBoards(boards, 'proj-a')).toBe('need_board');
    expect(readKanbanLastBoardId('proj-a')).toBeNull();
  });

  it('allows send when sole board without saved id', () => {
    expect(resolveKanbanSendBlockReasonFromBoards([{ board_id: 'only', name: 'Only' }], 'proj-a')).toBeNull();
  });

  it('builds board deep link with source chat and board id', () => {
    expect(
      buildKanbanBoardDeepLink({ sourceChatId: 'chat-1', boardId: 'board-9' }),
    ).toBe('/settings/kanban?source_chat=chat-1&board_id=board-9');
  });
});
