import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FONT_CHOICES, FONT_STORAGE_KEY, type FontId, getFontStack } from '@/lib/fonts';

describe('fonts module', () => {
  describe('FONT_CHOICES', () => {
    it('has exactly 3 font options', () => {
      expect(FONT_CHOICES).toHaveLength(3);
    });

    it('covers all FontId values', () => {
      const ids = FONT_CHOICES.map((f) => f.id);
      expect(ids).toEqual(['inter', 'system', 'atkinson']);
    });

    it('inter stack references --font-sans CSS variable', () => {
      const inter = FONT_CHOICES.find((f) => f.id === 'inter');
      expect(inter?.stack).toContain('var(--font-sans)');
    });

    it('system stack omits --font-sans (uses native fallbacks only)', () => {
      const system = FONT_CHOICES.find((f) => f.id === 'system');
      expect(system?.stack).not.toContain('var(--font-');
      expect(system?.stack).toContain('ui-sans-serif');
    });

    it('atkinson stack starts with the correct font name', () => {
      const atkinson = FONT_CHOICES.find((f) => f.id === 'atkinson');
      expect(atkinson?.stack).toContain('var(--font-atkinson');
    });

    it('all stacks include CJK fallbacks', () => {
      for (const choice of FONT_CHOICES) {
        expect(choice.stack).toContain('PingFang SC');
        expect(choice.stack).toContain('Noto Sans SC');
      }
    });
  });

  describe('getFontStack', () => {
    it('returns correct stack for each FontId', () => {
      for (const choice of FONT_CHOICES) {
        expect(getFontStack(choice.id)).toBe(choice.stack);
      }
    });

    it('falls back to custom font stack for custom string id', () => {
      const result = getFontStack('JetBrains Mono');
      expect(result).toContain('"JetBrains Mono"');
      expect(result).toContain('var(--font-sans)');
    });
  });

  describe('FONT_STORAGE_KEY', () => {
    it('is a non-empty string', () => {
      expect(typeof FONT_STORAGE_KEY).toBe('string');
      expect(FONT_STORAGE_KEY.length).toBeGreaterThan(0);
    });
  });
});
