import { describe, it, expect } from 'vitest';
import { PALETTE_COLORS, LINE_WIDTHS, MAX_UNDO_STEPS, MAX_IMAGE_DIMENSION } from '../tools/types';

describe('image-editor constants', () => {
  it('palette has 5 colors', () => {
    expect(PALETTE_COLORS).toHaveLength(5);
  });

  it('palette colors are valid hex', () => {
    for (const c of PALETTE_COLORS) {
      expect(c).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it('line widths has 2 options', () => {
    expect(LINE_WIDTHS).toHaveLength(2);
  });

  it('line widths are positive numbers', () => {
    for (const w of LINE_WIDTHS) {
      expect(w).toBeGreaterThan(0);
    }
  });

  it('max undo steps is reasonable', () => {
    expect(MAX_UNDO_STEPS).toBe(50);
  });

  it('max image dimension is 2048', () => {
    expect(MAX_IMAGE_DIMENSION).toBe(2048);
  });
});
