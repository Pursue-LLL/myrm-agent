import { describe, expect, it } from 'vitest';

import { PetState } from '../PetStateMachine';
import { resolvePetSheetRow } from '../petStateMapping';

describe('resolvePetSheetRow', () => {
  describe('Codex 9-row sheets', () => {
    const CODEX_ROWS = 9;

    it('maps IDLE to row 0 (idle)', () => {
      expect(resolvePetSheetRow(PetState.IDLE, CODEX_ROWS)).toBe(0);
    });

    it('maps RUNNING to row 7 (running)', () => {
      expect(resolvePetSheetRow(PetState.RUNNING, CODEX_ROWS)).toBe(7);
    });

    it('maps REVIEWING to row 8 (review)', () => {
      expect(resolvePetSheetRow(PetState.REVIEWING, CODEX_ROWS)).toBe(8);
    });

    it('maps JUMP to row 4 (jumping)', () => {
      expect(resolvePetSheetRow(PetState.JUMP, CODEX_ROWS)).toBe(4);
    });

    it('maps WAVE to row 3 (waving)', () => {
      expect(resolvePetSheetRow(PetState.WAVE, CODEX_ROWS)).toBe(3);
    });

    it('maps FAILED to row 5 (failed)', () => {
      expect(resolvePetSheetRow(PetState.FAILED, CODEX_ROWS)).toBe(5);
    });

    it('maps WAITING to row 6 (waiting)', () => {
      expect(resolvePetSheetRow(PetState.WAITING, CODEX_ROWS)).toBe(6);
    });
  });

  describe('Legacy 8-row sheets', () => {
    const LEGACY_ROWS = 8;

    it('maps IDLE to row 0 (idle)', () => {
      expect(resolvePetSheetRow(PetState.IDLE, LEGACY_ROWS)).toBe(0);
    });

    it('maps RUNNING to row 2 (run)', () => {
      expect(resolvePetSheetRow(PetState.RUNNING, LEGACY_ROWS)).toBe(2);
    });

    it('maps JUMP to row 5 (jump)', () => {
      expect(resolvePetSheetRow(PetState.JUMP, LEGACY_ROWS)).toBe(5);
    });

    it('maps WAVE to row 1 (wave)', () => {
      expect(resolvePetSheetRow(PetState.WAVE, LEGACY_ROWS)).toBe(1);
    });

    it('maps FAILED to row 3 (failed)', () => {
      expect(resolvePetSheetRow(PetState.FAILED, LEGACY_ROWS)).toBe(3);
    });

    it('maps REVIEWING to row 4 (review)', () => {
      expect(resolvePetSheetRow(PetState.REVIEWING, LEGACY_ROWS)).toBe(4);
    });

    it('maps WAITING to row 0 (idle fallback)', () => {
      expect(resolvePetSheetRow(PetState.WAITING, LEGACY_ROWS)).toBe(0);
    });
  });

  describe('edge cases', () => {
    it('returns 0 for unknown sheet with 1 row', () => {
      expect(resolvePetSheetRow(PetState.JUMP, 1)).toBe(0);
    });

    it('handles 0 rows gracefully', () => {
      expect(resolvePetSheetRow(PetState.IDLE, 0)).toBe(0);
    });
  });
});
