import { describe, expect, it } from 'vitest';

import { AnimRow } from '../PetStateMachine';
import { resolveAnimRow } from '../petStateMapping';

describe('resolveAnimRow', () => {
  describe('Codex 9-row sheets', () => {
    const CODEX_ROWS = 9;

    it('maps IDLE to row 0 (idle)', () => {
      expect(resolveAnimRow(AnimRow.IDLE, CODEX_ROWS)).toBe(0);
    });

    it('maps RUNNING to row 7 (running)', () => {
      expect(resolveAnimRow(AnimRow.RUNNING, CODEX_ROWS)).toBe(7);
    });

    it('maps SLEEPING to row 0 (idle fallback)', () => {
      expect(resolveAnimRow(AnimRow.SLEEPING, CODEX_ROWS)).toBe(0);
    });

    it('maps CODING to row 7 (running)', () => {
      expect(resolveAnimRow(AnimRow.CODING, CODEX_ROWS)).toBe(7);
    });

    it('maps THINKING to row 8 (review)', () => {
      expect(resolveAnimRow(AnimRow.THINKING, CODEX_ROWS)).toBe(8);
    });

    it('maps CELEBRATING to row 4 (jumping)', () => {
      expect(resolveAnimRow(AnimRow.CELEBRATING, CODEX_ROWS)).toBe(4);
    });

    it('maps FAILED to row 5 (failed)', () => {
      expect(resolveAnimRow(AnimRow.FAILED, CODEX_ROWS)).toBe(5);
    });

    it('maps REVIEWING to row 8 (review)', () => {
      expect(resolveAnimRow(AnimRow.REVIEWING, CODEX_ROWS)).toBe(8);
    });

    it('maps WAVING to row 3 (waving)', () => {
      expect(resolveAnimRow(AnimRow.WAVING, CODEX_ROWS)).toBe(3);
    });
  });

  describe('Legacy 8-row sheets', () => {
    const LEGACY_ROWS = 8;

    it('maps IDLE to row 0 (idle)', () => {
      expect(resolveAnimRow(AnimRow.IDLE, LEGACY_ROWS)).toBe(0);
    });

    it('maps RUNNING to row 2 (run)', () => {
      expect(resolveAnimRow(AnimRow.RUNNING, LEGACY_ROWS)).toBe(2);
    });

    it('maps CELEBRATING to row 5 (jump)', () => {
      expect(resolveAnimRow(AnimRow.CELEBRATING, LEGACY_ROWS)).toBe(5);
    });

    it('maps FAILED to row 3 (failed)', () => {
      expect(resolveAnimRow(AnimRow.FAILED, LEGACY_ROWS)).toBe(3);
    });

    it('maps REVIEWING to row 4 (review)', () => {
      expect(resolveAnimRow(AnimRow.REVIEWING, LEGACY_ROWS)).toBe(4);
    });

    it('maps WAVING to row 1 (wave)', () => {
      expect(resolveAnimRow(AnimRow.WAVING, LEGACY_ROWS)).toBe(1);
    });
  });

  describe('edge cases', () => {
    it('returns 0 for unknown sheet with 1 row', () => {
      expect(resolveAnimRow(AnimRow.CELEBRATING, 1)).toBe(0);
    });

    it('handles 0 rows gracefully', () => {
      expect(resolveAnimRow(AnimRow.IDLE, 0)).toBe(0);
    });

    it('handles very large row counts as Codex', () => {
      expect(resolveAnimRow(AnimRow.RUNNING, 20)).toBe(7);
    });
  });
});
