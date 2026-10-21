import { describe, expect, it } from 'vitest';
import { derivePalette, meetsContrast, relativeLuminance, resolveContrastSafeForeground } from '../oklch';
import { compileThemeProfile } from '../compiler';
import { getDefaultThemeProfile } from '../presets';

describe('derivePalette', () => {
  const HEX_RE = /^#[0-9a-f]{6}$/;

  it('returns valid hex strings for all palette tokens', () => {
    const palette = derivePalette('#2563eb');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
    expect(palette.primaryHoverLight).toMatch(HEX_RE);
    expect(palette.primaryHoverDark).toMatch(HEX_RE);
    expect(palette.primaryDarkLight).toMatch(HEX_RE);
    expect(palette.primaryDarkDark).toMatch(HEX_RE);
    expect(palette.dualAccent).toBe(false);
  });

  it('produces distinct light/dark variants', () => {
    const palette = derivePalette('#2563eb');
    expect(palette.primaryLight).not.toBe(palette.primaryDark);
    expect(palette.primaryHoverLight).not.toBe(palette.primaryHoverDark);
  });

  it('handles pure red', () => {
    const palette = derivePalette('#ff0000');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('handles pure green', () => {
    const palette = derivePalette('#00ff00');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('handles near-black without crashing', () => {
    const palette = derivePalette('#0a0a0a');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('handles near-white without crashing', () => {
    const palette = derivePalette('#f5f5f5');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('handles pure black edge case', () => {
    const palette = derivePalette('#000000');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('handles pure white edge case', () => {
    const palette = derivePalette('#ffffff');
    expect(palette.primaryLight).toMatch(HEX_RE);
    expect(palette.primaryDark).toMatch(HEX_RE);
  });

  it('produces consistent output for same input', () => {
    const a = derivePalette('#7c3aed');
    const b = derivePalette('#7c3aed');
    expect(a).toEqual(b);
  });

  it('light variant has lower luminance than dark variant', () => {
    const palette = derivePalette('#2563eb');
    const lumLight = relativeLuminance(palette.primaryLight);
    const lumDark = relativeLuminance(palette.primaryDark);
    expect(lumDark).toBeGreaterThan(lumLight);
  });

  it('primaryLight meets WCAG contrast against white bg', () => {
    const palette = derivePalette('#2563eb');
    expect(meetsContrast(palette.primaryLight, '#ffffff', 3)).toBe(true);
  });

  it('handles lowercase hex input', () => {
    const palette = derivePalette('#abcdef');
    expect(palette.primaryLight).toMatch(HEX_RE);
  });

  it('handles uppercase hex input', () => {
    const palette = derivePalette('#ABCDEF');
    expect(palette.primaryLight).toMatch(HEX_RE);
  });

  it('handles mixed case hex input', () => {
    const a = derivePalette('#AbCdEf');
    const b = derivePalette('#abcdef');
    expect(a).toEqual(b);
  });

  it('hover variant is darker than primary in light mode', () => {
    const palette = derivePalette('#2563eb');
    const lumPrimary = relativeLuminance(palette.primaryLight);
    const lumHover = relativeLuminance(palette.primaryHoverLight);
    expect(lumHover).toBeLessThan(lumPrimary);
  });

  it('darkDark variant matches primaryLight lightness level', () => {
    const palette = derivePalette('#2563eb');
    expect(palette.primaryDarkDark).toBe(palette.primaryLight);
  });

  it('derived palette compiles for both light and dark color schemes', () => {
    const palette = derivePalette('#e07830');
    const base = getDefaultThemeProfile();
    const recipe = { ...base, id: 'test-custom', name: 'Custom', palette, builtin: false };

    const light = compileThemeProfile(recipe, {
      colorScheme: 'light',
      layoutId: 'full-bleed',
      sceneId: 'immersive',
      prefersReducedMotion: false,
      isMobile: false,
    });
    const dark = compileThemeProfile(recipe, {
      colorScheme: 'dark',
      layoutId: 'full-bleed',
      sceneId: 'immersive',
      prefersReducedMotion: false,
      isMobile: false,
    });

    expect(light.cssVariables['--primary']).toBe(palette.primaryLight);
    expect(dark.cssVariables['--primary']).toBe(palette.primaryDark);
    expect(light.cssVariables['--primary']).not.toBe(dark.cssVariables['--primary']);
    expect(light.dataAttributes['data-myrm-theme-profile']).toBe('test-custom');
    expect(dark.dataAttributes['data-myrm-theme-profile']).toBe('test-custom');
  });

  it('all builtin preset primary hex values derive valid palettes', () => {
    const presetColors = [
      '#588e95',
      '#c4567a',
      '#b4762c',
      '#7c4dba',
      '#2563eb',
      '#4a7d84',
      '#7a9a8e',
      '#8b7355',
      '#5a7a5e',
      '#c06030',
      '#4a6a9a',
      '#2a9a48',
      '#6a6a72',
      '#c87060',
      '#a08860',
      '#3a9a8a',
    ];
    for (const hex of presetColors) {
      const palette = derivePalette(hex);
      expect(palette.primaryLight).toMatch(HEX_RE);
      expect(palette.primaryDark).toMatch(HEX_RE);
      expect(palette.primaryLight).not.toBe(palette.primaryDark);
    }
  });
});

describe('resolveContrastSafeForeground', () => {
  it('meets WCAG AA for official default light primary', () => {
    const foreground = resolveContrastSafeForeground('#588e95');
    expect(meetsContrast(foreground, '#588e95')).toBe(true);
  });

  it('meets WCAG AA for mid-gray backgrounds via lightness sweep', () => {
    const foreground = resolveContrastSafeForeground('#777777');
    expect(meetsContrast(foreground, '#777777')).toBe(true);
  });
});
