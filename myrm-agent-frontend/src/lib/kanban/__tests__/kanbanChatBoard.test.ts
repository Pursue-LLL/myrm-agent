import { describe, expect, it, beforeEach, afterEach } from 'vitest';

import {
  KANBAN_LAST_BOARD_ID_KEY,
  readKanbanLastBoardId,
  resolveKanbanChatBoardId,
  resolveKanbanDefaultBoardIdForRequest,
  resolveKanbanSendBlockReasonFromBoards,
  shouldShowKanbanBoardPicker,
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

  it('auto-picks sole board', () => {
    const boards = [{ board_id: 'only', name: 'Only' }];
    expect(resolveKanbanChatBoardId(boards)).toBe('only');
    expect(shouldShowKanbanBoardPicker(boards)).toBe(false);
  });

  it('uses saved board when valid among many', () => {
    writeKanbanLastBoardId('b2');
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanChatBoardId(boards)).toBe('b2');
    expect(shouldShowKanbanBoardPicker(boards)).toBe(false);
  });

  it('requires picker when multiple boards and no valid saved id', () => {
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanChatBoardId(boards)).toBeNull();
    expect(shouldShowKanbanBoardPicker(boards)).toBe(true);
  });

  it('includes board id in request only when kanban enabled', () => {
    writeKanbanLastBoardId('board-x');
    expect(resolveKanbanDefaultBoardIdForRequest(['web_search'])).toBeUndefined();
    expect(resolveKanbanDefaultBoardIdForRequest(['kanban'])).toBe('board-x');
  });

  it('blocks send when no boards exist', () => {
    expect(resolveKanbanSendBlockReasonFromBoards([])).toBe('no_boards');
  });

  it('blocks send when multiple boards and no selection', () => {
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanSendBlockReasonFromBoards(boards)).toBe('need_board');
  });

  it('clears stale saved id and blocks when board was deleted', () => {
    writeKanbanLastBoardId('deleted-board');
    const boards = [
      { board_id: 'b1', name: 'One' },
      { board_id: 'b2', name: 'Two' },
    ];
    expect(resolveKanbanSendBlockReasonFromBoards(boards)).toBe('need_board');
    expect(readKanbanLastBoardId()).toBeNull();
  });

  it('allows send when sole board without saved id', () => {
    expect(resolveKanbanSendBlockReasonFromBoards([{ board_id: 'only', name: 'Only' }])).toBeNull();
  });
});
