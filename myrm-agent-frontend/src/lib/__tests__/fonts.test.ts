import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-sans', className: 'mock-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-mono', className: 'mock-jbm' }),
}));

import {
  FONT_CHOICES,
  FONT_STORAGE_KEY,
  type FontId,
  getFontStack,
  ensureFontLoaded,
  fontSans,
  fontMono,
} from '@/lib/fonts';

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
      const inter = FONT_CHOICES.find((f) => f.id === 'inter')!;
      expect(inter.stack).toContain('var(--font-sans)');
    });

    it('system stack omits --font-sans (uses native fallbacks only)', () => {
      const system = FONT_CHOICES.find((f) => f.id === 'system')!;
      expect(system.stack).not.toContain('var(--font-');
      expect(system.stack).toContain('ui-sans-serif');
    });

    it('atkinson stack starts with the correct font name', () => {
      const atkinson = FONT_CHOICES.find((f) => f.id === 'atkinson')!;
      expect(atkinson.stack).toMatch(/^"Atkinson Hyperlegible Next"/);
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

    it('falls back to inter stack for unknown id', () => {
      const result = getFontStack('nonexistent' as FontId);
      expect(result).toBe(FONT_CHOICES[0].stack);
    });
  });

  describe('FONT_STORAGE_KEY', () => {
    it('is a non-empty string', () => {
      expect(typeof FONT_STORAGE_KEY).toBe('string');
      expect(FONT_STORAGE_KEY.length).toBeGreaterThan(0);
    });
  });

  describe('font instances', () => {
    it('fontSans has --font-sans variable', () => {
      expect(fontSans.variable).toBe('--font-sans');
    });

    it('fontMono has --font-mono variable', () => {
      expect(fontMono.variable).toBe('--font-mono');
    });
  });

  describe('ensureFontLoaded', () => {
    let appendChildSpy: ReturnType<typeof vi.spyOn>;
    let createElementSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      const mockLink = { rel: '', href: '' };
      createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue(mockLink as unknown as HTMLElement);
      appendChildSpy = vi.spyOn(document.head, 'appendChild').mockImplementation((node) => node);
    });

    afterEach(() => {
      createElementSpy.mockRestore();
      appendChildSpy.mockRestore();
    });

    it('does not load for inter (no external URL)', () => {
      ensureFontLoaded('inter');
      expect(appendChildSpy).not.toHaveBeenCalled();
    });

    it('does not load for system (no external URL)', () => {
      ensureFontLoaded('system');
      expect(appendChildSpy).not.toHaveBeenCalled();
    });

    it('loads stylesheet for atkinson on first call', () => {
      ensureFontLoaded('atkinson');
      expect(createElementSpy).toHaveBeenCalledWith('link');
      expect(appendChildSpy).toHaveBeenCalledTimes(1);
    });
  });
});
