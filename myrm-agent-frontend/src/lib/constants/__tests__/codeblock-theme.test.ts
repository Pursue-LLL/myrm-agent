/**
 * [INPUT]
 * - lib/constants/codeblock-theme: `INLINE_CODE_CHIP` and `CODE_BLOCK_THEME` under test
 * - theme-engine/oklch::contrastRatio: the product's WCAG contrast function
 * - node_modules/tailwindcss/theme.css: the palette the chip's colour classes name
 * [OUTPUT]
 * Vitest: the inline code chip sits on the same surface as a code block and its text reaches 4.5:1 on it, in both
 * appearances.
 * [POS]
 * Guard of the chip's contrast. A palette step swapped for a lighter one, or a chip surface that drifts away from the
 * code block's, shows up here as a named colour-on-surface pair instead of an orange word that is hard to read.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { contrastRatio } from '@/theme-engine/oklch';
import { CODE_BLOCK_THEME, INLINE_CODE_CHIP } from '../codeblock-theme';

const MIN_CONTRAST = 4.5;

const tailwindTheme = readFileSync(resolve(process.cwd(), 'node_modules/tailwindcss/theme.css'), 'utf8');

/** A step of Tailwind's palette, such as `orange-700`, as `#rrggbb` (the palette is written in oklch). */
function paletteHex(step: string): string {
  const parts = tailwindTheme.match(new RegExp(`--color-${step}:\\s*oklch\\(([\\d.]+)%\\s+([\\d.]+)\\s+([\\d.]+)\\)`));
  if (!parts) {
    throw new Error(`--color-${step} is not an oklch colour of the Tailwind palette`);
  }
  const lightness = Number(parts[1]) / 100;
  const hue = (Number(parts[3]) * Math.PI) / 180;
  const a = Number(parts[2]) * Math.cos(hue);
  const b = Number(parts[2]) * Math.sin(hue);
  const [l, m, s] = [
    lightness + 0.3963377774 * a + 0.2158037573 * b,
    lightness - 0.1055613458 * a - 0.0638541728 * b,
    lightness - 0.0894841775 * a - 1.291485548 * b,
  ].map((cone) => cone ** 3) as [number, number, number];
  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const encode = (value: number): number => {
    const clamped = Math.min(1, Math.max(0, value));
    return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
  };
  return `#${linear
    .map((value) =>
      Math.round(encode(value) * 255)
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`;
}

/** The first capture of `pattern` in `classes`, or a failure naming what is missing. */
function classOf(classes: string, pattern: RegExp, what: string): string {
  const found = classes.match(pattern)?.[1];
  if (found === undefined) {
    throw new Error(`${what} is not among the classes: ${classes}`);
  }
  return found;
}

describe('palette conversion', () => {
  it('agrees with the colour the dark code block surface is drawn with in the browser', () => {
    expect(paletteHex('gray-800')).toBe('#1e2939');
  });
});

describe('inline code chip', () => {
  const lightSurface = classOf(INLINE_CODE_CHIP, /(?:^|\s)bg-\[(#[0-9a-f]{6})\]/i, 'the light surface');
  const darkSurface = paletteHex(classOf(INLINE_CODE_CHIP, /dark:bg-([a-z]+-\d+)/, 'the dark surface'));
  const lightText = paletteHex(classOf(INLINE_CODE_CHIP, /(?:^|\s)text-([a-z]+-\d+)(?=\s|$)/, 'the light text colour'));
  const darkText = paletteHex(classOf(INLINE_CODE_CHIP, /dark:text-([a-z]+-\d+)/, 'the dark text colour'));

  it('sits on the same surfaces as a code block', () => {
    expect(CODE_BLOCK_THEME.light.background).toBe(`bg-[${lightSurface}]`);
    expect(paletteHex(CODE_BLOCK_THEME.dark.background.replace('bg-', ''))).toBe(darkSurface);
  });

  it.each([
    ['light', lightText, lightSurface],
    ['dark', darkText, darkSurface],
  ])('reaches 4.5:1 in the %s appearance', (_appearance, text, surface) => {
    expect(contrastRatio(text, surface), `${text} on ${surface}`).toBeGreaterThanOrEqual(MIN_CONTRAST);
  });
});
