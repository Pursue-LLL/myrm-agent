import { describe, it, expect, beforeEach, afterEach } from 'vitest';

const LS_KEYS = {
  viewMode: 'kanban_view_mode',
  laneByProfile: 'kanban_lane_by_profile',
  lastBoardId: 'kanban_last_board_id',
} as const;

type ViewMode = 'board' | 'graph' | 'activity';
const VALID_MODES: ViewMode[] = ['board', 'graph', 'activity'];

function readViewMode(): ViewMode {
  if (typeof window === 'undefined') return 'board';
  try {
    const stored = localStorage.getItem(LS_KEYS.viewMode);
    if (stored === 'board' || stored === 'graph' || stored === 'activity') return stored;
  } catch { /* private mode / quota */ }
  return 'board';
}

function writeViewMode(mode: ViewMode): void {
  try { localStorage.setItem(LS_KEYS.viewMode, mode); } catch { /* ignore */ }
}

function readLaneByProfile(): boolean {
  if (typeof window === 'undefined') return true;
  try { return localStorage.getItem(LS_KEYS.laneByProfile) !== 'false'; } catch { return true; }
}

function writeLaneByProfile(value: boolean): void {
  try { localStorage.setItem(LS_KEYS.laneByProfile, String(value)); } catch { /* ignore */ }
}

interface MinimalBoard { board_id: string }

function writeLastBoardId(board: MinimalBoard | null): void {
  try {
    if (board) localStorage.setItem(LS_KEYS.lastBoardId, board.board_id);
    else localStorage.removeItem(LS_KEYS.lastBoardId);
  } catch { /* ignore */ }
}

function restoreLastBoard<T extends MinimalBoard>(
  boards: T[],
  loading: boolean,
  selectedBoard: T | null,
): T | null {
  if (loading || selectedBoard || boards.length === 0) return null;
  try {
    const lastId = localStorage.getItem(LS_KEYS.lastBoardId);
    if (!lastId) return null;
    const match = boards.find((b) => b.board_id === lastId);
    if (match) return match;
    localStorage.removeItem(LS_KEYS.lastBoardId);
  } catch { /* ignore */ }
  return null;
}

describe('Kanban localStorage preference persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('kanban_view_mode', () => {
    it('stores and retrieves all valid view modes', () => {
      for (const mode of VALID_MODES) {
        localStorage.setItem(LS_KEYS.viewMode, mode);
        expect(readViewMode()).toBe(mode);
      }
    });

    it('defaults to board when key is absent', () => {
      expect(localStorage.getItem(LS_KEYS.viewMode)).toBeNull();
      expect(readViewMode()).toBe('board');
    });

    it('defaults to board when stored value is invalid', () => {
      localStorage.setItem(LS_KEYS.viewMode, 'invalid_mode');
      expect(readViewMode()).toBe('board');
    });

    it('defaults to board when stored value is empty string', () => {
      localStorage.setItem(LS_KEYS.viewMode, '');
      expect(readViewMode()).toBe('board');
    });

    it('defaults to board when stored value is numeric', () => {
      localStorage.setItem(LS_KEYS.viewMode, '42');
      expect(readViewMode()).toBe('board');
    });

    it('defaults to board when stored value is whitespace', () => {
      localStorage.setItem(LS_KEYS.viewMode, '  board  ');
      expect(readViewMode()).toBe('board');
    });

    it('overwrites previous value on tab switch', () => {
      writeViewMode('board');
      writeViewMode('graph');
      expect(readViewMode()).toBe('graph');
    });

    it('round-trips board → graph → activity → board', () => {
      for (const mode of ['board', 'graph', 'activity', 'board'] as const) {
        writeViewMode(mode);
        expect(readViewMode()).toBe(mode);
      }
    });
  });

  describe('kanban_lane_by_profile', () => {
    it('defaults to true when key is absent', () => {
      expect(localStorage.getItem(LS_KEYS.laneByProfile)).toBeNull();
      expect(readLaneByProfile()).toBe(true);
    });

    it('reads false when stored as "false"', () => {
      writeLaneByProfile(false);
      expect(readLaneByProfile()).toBe(false);
    });

    it('reads true when stored as "true"', () => {
      writeLaneByProfile(true);
      expect(readLaneByProfile()).toBe(true);
    });

    it('reads true for non-standard stored values (not "false")', () => {
      localStorage.setItem(LS_KEYS.laneByProfile, 'yes');
      expect(readLaneByProfile()).toBe(true);

      localStorage.setItem(LS_KEYS.laneByProfile, '0');
      expect(readLaneByProfile()).toBe(true);

      localStorage.setItem(LS_KEYS.laneByProfile, '');
      expect(readLaneByProfile()).toBe(true);
    });

    it('toggles true → false → true correctly', () => {
      writeLaneByProfile(true);
      expect(readLaneByProfile()).toBe(true);

      const next1 = !readLaneByProfile();
      writeLaneByProfile(next1);
      expect(readLaneByProfile()).toBe(false);

      const next2 = !readLaneByProfile();
      writeLaneByProfile(next2);
      expect(readLaneByProfile()).toBe(true);
    });
  });

  describe('kanban_last_board_id', () => {
    it('stores a board_id and retrieves it', () => {
      writeLastBoardId({ board_id: 'board-abc-123' });
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-abc-123');
    });

    it('removes key when board is null (navigate back)', () => {
      writeLastBoardId({ board_id: 'board-abc' });
      writeLastBoardId(null);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBeNull();
    });

    it('overwrites old board_id on board switch', () => {
      writeLastBoardId({ board_id: 'board-old' });
      writeLastBoardId({ board_id: 'board-new' });
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-new');
    });
  });

  describe('board restore logic (useEffect simulation)', () => {
    const boards: MinimalBoard[] = [
      { board_id: 'board-1' },
      { board_id: 'board-2' },
      { board_id: 'board-3' },
    ];

    it('restores matching board when lastId exists', () => {
      localStorage.setItem(LS_KEYS.lastBoardId, 'board-2');
      const restored = restoreLastBoard(boards, false, null);
      expect(restored).toEqual({ board_id: 'board-2' });
    });

    it('clears stale lastId when board not found', () => {
      localStorage.setItem(LS_KEYS.lastBoardId, 'board-deleted-999');
      const restored = restoreLastBoard(boards, false, null);
      expect(restored).toBeNull();
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBeNull();
    });

    it('returns null when no lastId stored', () => {
      const restored = restoreLastBoard(boards, false, null);
      expect(restored).toBeNull();
    });

    it('skips restore while loading', () => {
      localStorage.setItem(LS_KEYS.lastBoardId, 'board-1');
      const restored = restoreLastBoard(boards, true, null);
      expect(restored).toBeNull();
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-1');
    });

    it('skips restore when selectedBoard already set', () => {
      localStorage.setItem(LS_KEYS.lastBoardId, 'board-2');
      const existing = { board_id: 'board-1' };
      const restored = restoreLastBoard(boards, false, existing);
      expect(restored).toBeNull();
    });

    it('skips restore when boards list is empty', () => {
      localStorage.setItem(LS_KEYS.lastBoardId, 'board-1');
      const restored = restoreLastBoard([], false, null);
      expect(restored).toBeNull();
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-1');
    });

    it('delete selected board → selectBoard(null) → localStorage cleared', () => {
      writeLastBoardId({ board_id: 'board-2' });
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-2');
      writeLastBoardId(null);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBeNull();
    });
  });

  describe('cross-key isolation', () => {
    it('different keys do not interfere with each other', () => {
      writeViewMode('graph');
      writeLaneByProfile(false);
      writeLastBoardId({ board_id: 'board-xyz' });

      expect(readViewMode()).toBe('graph');
      expect(readLaneByProfile()).toBe(false);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-xyz');

      writeLastBoardId(null);
      expect(readViewMode()).toBe('graph');
      expect(readLaneByProfile()).toBe(false);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBeNull();
    });

    it('clearing one key does not affect others', () => {
      writeViewMode('activity');
      writeLaneByProfile(true);
      writeLastBoardId({ board_id: 'board-1' });

      localStorage.removeItem(LS_KEYS.viewMode);
      expect(readViewMode()).toBe('board');
      expect(readLaneByProfile()).toBe(true);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBe('board-1');
    });

    it('localStorage.clear() resets all to defaults', () => {
      writeViewMode('graph');
      writeLaneByProfile(false);
      writeLastBoardId({ board_id: 'board-1' });

      localStorage.clear();
      expect(readViewMode()).toBe('board');
      expect(readLaneByProfile()).toBe(true);
      expect(localStorage.getItem(LS_KEYS.lastBoardId)).toBeNull();
    });
  });

  describe('try-catch robustness', () => {
    it('viewMode getItem throws → defaults to board', () => {
      const original = localStorage.getItem.bind(localStorage);
      localStorage.getItem = () => { throw new Error('QuotaExceeded'); };

      expect(readViewMode()).toBe('board');
      localStorage.getItem = original;
    });

    it('laneByProfile getItem throws → defaults to true', () => {
      const original = localStorage.getItem.bind(localStorage);
      localStorage.getItem = () => { throw new Error('SecurityError'); };

      expect(readLaneByProfile()).toBe(true);
      localStorage.getItem = original;
    });

    it('setItem failure does not crash write functions', () => {
      const proto = Object.getPrototypeOf(localStorage);
      const original = proto.setItem;
      proto.setItem = () => { throw new Error('QuotaExceeded'); };

      expect(() => writeViewMode('graph')).not.toThrow();
      expect(() => writeLaneByProfile(false)).not.toThrow();
      expect(() => writeLastBoardId({ board_id: 'x' })).not.toThrow();

      proto.setItem = original;
    });

    it('removeItem failure does not crash writeLastBoardId(null)', () => {
      const original = localStorage.removeItem.bind(localStorage);
      Object.defineProperty(localStorage, 'removeItem', {
        value: () => { throw new Error('SecurityError'); },
        writable: true, configurable: true,
      });

      expect(() => writeLastBoardId(null)).not.toThrow();

      Object.defineProperty(localStorage, 'removeItem', {
        value: original, writable: true, configurable: true,
      });
    });

    it('restoreLastBoard handles getItem failure gracefully', () => {
      const original = localStorage.getItem.bind(localStorage);
      localStorage.getItem = () => { throw new Error('SecurityError'); };

      const boards = [{ board_id: 'board-1' }];
      const result = restoreLastBoard(boards, false, null);
      expect(result).toBeNull();

      localStorage.getItem = original;
    });
  });

  describe('key naming convention', () => {
    it('all keys use kanban_ prefix', () => {
      for (const key of Object.values(LS_KEYS)) {
        expect(key).toMatch(/^kanban_/);
      }
    });

    it('keys are snake_case', () => {
      for (const key of Object.values(LS_KEYS)) {
        expect(key).toMatch(/^[a-z][a-z0-9_]*$/);
      }
    });
  });
});
