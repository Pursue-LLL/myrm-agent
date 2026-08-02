import { describe, expect, it } from 'vitest';
import {
  parseThemeRecipeJson,
  ThemeRecipeParseError,
  getDefaultThemeProfile,
} from '@/theme-engine';

describe('parseThemeRecipeJson', () => {
  const validRecipe = {
    name: 'Ocean calm',
    layoutId: 'nav-rail-focus',
    fontId: 'atkinson',
    palette: {
      primaryLight: '#112233',
      primaryDark: '#223344',
      primaryHoverLight: '#334455',
      primaryHoverDark: '#445566',
      primaryDarkLight: '#556677',
      primaryDarkDark: '#667788',
      dualAccent: false,
    },
    art: {
      mediaKind: 'none',
      focusX: 0.5,
      focusY: 0.4,
      wash: 0.5,
    },
  };

  it('parses fenced JSON from skill output', () => {
    const raw = `\`\`\`json\n${JSON.stringify(validRecipe)}\n\`\`\``;
    const parsed = parseThemeRecipeJson(raw);
    expect(parsed.name).toBe('Ocean calm');
    expect(parsed.layoutId).toBe('nav-rail-focus');
    expect(parsed.fontId).toBe('atkinson');
  });

  it('rejects invalid layoutId', () => {
    expect(() =>
      parseThemeRecipeJson(JSON.stringify({ ...validRecipe, layoutId: 'invalid' })),
    ).toThrow(ThemeRecipeParseError);
  });

  it('rejects missing name', () => {
    expect(() =>
      parseThemeRecipeJson(JSON.stringify({ ...validRecipe, name: '' })),
    ).toThrow(ThemeRecipeParseError);
  });

  it('falls back art fields from default profile', () => {
    const parsed = parseThemeRecipeJson(JSON.stringify(validRecipe));
    const fallback = getDefaultThemeProfile();
    expect(parsed.art?.wash).toBe(0.5);
    expect(parsed.art?.focusX).toBe(0.5);
    expect(parsed.art?.mediaKind).toBe('none');
    expect(fallback.art.wash).toBeDefined();
  });

  it('clamps wash to server-valid range', () => {
    const parsed = parseThemeRecipeJson(
      JSON.stringify({
        ...validRecipe,
        art: { ...validRecipe.art, wash: 0.05 },
      }),
    );
    expect(parsed.art?.wash).toBe(0.2);
  });

  it('rejects non-file assetRef from skill JSON', () => {
    expect(() =>
      parseThemeRecipeJson(
        JSON.stringify({
          ...validRecipe,
          art: { ...validRecipe.art, mediaKind: 'image', assetRef: 'hero.png' },
        }),
      ),
    ).toThrow(ThemeRecipeParseError);
  });
});
