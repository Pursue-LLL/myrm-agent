/**
 * [INPUT]
 * - lib/syntax/theme: the syntax themes under test
 * - theme-engine/oklch::contrastRatio: the product's WCAG contrast function
 * - src/app/globals.css: the `--foreground` and `--muted-foreground` tokens the line numbers are drawn with
 * [OUTPUT]
 * Vitest: every colour of the syntax themes reaches 4.5:1 on every surface the product draws code on, in both
 * appearances, including the tinted rows of diffs; the themes differ from the stock ones in colours only.
 * [POS]
 * Guard of the contrast bar. A stock colour that slips back in (a replacement key that stopped matching after an
 * upgrade of prism-react-renderer, a new surface or tint) shows up here as a named colour-on-surface pair, where in
 * the app it would be a comment or a string that is hard to read.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { themes } from 'prism-react-renderer';
import { describe, expect, it } from 'vitest';

import { contrastRatio } from '@/theme-engine/oklch';
import { SYNTAX_THEME_DARK, SYNTAX_THEME_LIGHT, syntaxThemeFor, type SyntaxTheme } from '../theme';

const MIN_CONTRAST = 4.5;

const globalsCss = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

/** The value of a custom property in the `:root` (light) or `.dark` block of globals.css. */
function token(block: ':root' | '.dark', name: string): string {
  const from = globalsCss.indexOf(`\n${block} {`);
  const value = globalsCss.slice(from).match(new RegExp(`\\n\\s+${name}:\\s*([^;]+);`))?.[1];
  if (from === -1 || value === undefined) {
    throw new Error(`${name} is not defined in the ${block} block of globals.css`);
  }
  return value.trim();
}

/** `color-mix(in srgb, var(--foreground) 60%, transparent)` -> 0.6 */
function mutedForegroundAlpha(): number {
  const percent = token(':root', '--muted-foreground').match(/var\(--foreground\)\s+(\d+)%/)?.[1];
  if (percent === undefined) {
    throw new Error('--muted-foreground is no longer a mix of --foreground and transparent');
  }
  return Number(percent) / 100;
}

function hexOf(rgb: readonly [number, number, number]): string {
  return `#${rgb.map((channel) => Math.round(channel).toString(16).padStart(2, '0')).join('')}`;
}

function rgbOf(hex: string): [number, number, number] {
  return [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16)) as [number, number, number];
}

/** `hsl(230, 4%, 64%)`, the form the stock themes write their colours in, or a `#rrggbb`, as a `#rrggbb`. */
function toHex(color: string): string {
  if (color.startsWith('#')) {
    return color;
  }
  const parts = color.match(/^hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)$/);
  if (!parts) {
    throw new Error(`unsupported colour: ${color}`);
  }
  const hue = Number(parts[1]);
  const saturation = Number(parts[2]) / 100;
  const lightness = Number(parts[3]) / 100;
  const chroma = saturation * Math.min(lightness, 1 - lightness);
  const channel = (offset: number): number => {
    const k = (offset + hue / 30) % 12;
    return (lightness - chroma * Math.max(-1, Math.min(k - 3, 9 - k, 1))) * 255;
  };
  return hexOf([channel(0), channel(8), channel(4)]);
}

/** `foreground` at `alpha` over an opaque `base`. */
function over(foreground: string, alpha: number, base: string): string {
  const [front, back] = [rgbOf(foreground), rgbOf(base)];
  return hexOf(front.map((channel, at) => alpha * channel + (1 - alpha) * (back[at] ?? 0)) as [number, number, number]);
}

/** The colour a token of `type` gets: the last rule of the theme that names the type and sets a colour. */
function colorOfType(theme: SyntaxTheme, type: string): string {
  const rule = theme.styles.filter((entry) => entry.types.includes(type) && entry.style.color !== undefined).at(-1);
  if (rule?.style.color === undefined) {
    throw new Error(`the theme has no colour for ${type}`);
  }
  return toHex(rule.style.color);
}

function themeColors(theme: SyntaxTheme): string[] {
  const colors = [theme.plain.color, ...theme.styles.map((entry) => entry.style.color)];
  return [...new Set(colors.filter((color): color is string => color !== undefined).map(toHex))];
}

interface Appearance {
  theme: SyntaxTheme;
  foreground: string;
  /** Opacity of the row tint (`bg-green-500/10` in light, `/20` in dark). */
  tintAlpha: number;
  /** `--background`: the workspace file view and the diff viewer. */
  panel: string;
  /** The chat code block's own background (`CODE_BLOCK_THEME`). */
  codeBlock: string;
  /** The step panel's `bg-zinc-50/50` / `dark:bg-zinc-900/50` over the panel. */
  stepPanel: string;
  /** `hover:bg-muted/50` over the panel, a row of the diff viewer under the pointer. */
  hoveredRow: string;
}

function appearance(block: ':root' | '.dark', theme: SyntaxTheme, codeBlock: string, zinc: string): Appearance {
  const panel = token(block, '--background');
  const muted = token(block, '--muted');
  const mutedAlpha = muted.length === 9 ? Number.parseInt(muted.slice(7), 16) / 255 : 1;
  return {
    theme,
    foreground: token(block, '--foreground'),
    tintAlpha: block === ':root' ? 0.1 : 0.2,
    panel,
    codeBlock,
    stepPanel: over(zinc, 0.5, panel),
    hoveredRow: over(muted.slice(0, 7), 0.5 * mutedAlpha, panel),
  };
}

const APPEARANCES: Record<'light' | 'dark', Appearance> = {
  light: appearance(':root', SYNTAX_THEME_LIGHT, '#f6f6f1', '#fafafa'),
  dark: appearance('.dark', SYNTAX_THEME_DARK, '#1e2939', '#18181b'),
};

const TINTS = { addition: '#00c950', deletion: '#fb2c36', hunk: '#2b7fff' } as const;

/** A colour as it appears on a surface of the product, named for the failure message. */
interface Drawn {
  color: string;
  surface: string;
  background: string;
}

function ratioOf({ color, background }: Drawn): number {
  return contrastRatio(color, background);
}

function describeDrawn(drawn: Drawn): string {
  return `${drawn.color} on ${drawn.surface} (${drawn.background}): ${ratioOf(drawn).toFixed(2)}`;
}

/** The surfaces a code token of any colour can land on: the plain surfaces and the diff viewer's rows with their tints. */
function anyTokenSurfaces(look: Appearance): Record<string, string> {
  return {
    panel: look.panel,
    'chat code block': look.codeBlock,
    'step panel': look.stepPanel,
    'hovered diff row': look.hoveredRow,
    'added diff row': over(TINTS.addition, look.tintAlpha, look.panel),
    'removed diff row': over(TINTS.deletion, look.tintAlpha, look.panel),
  };
}

/** The tinted rows of a diff code block, where only the colours of the diff grammar's tokens appear. */
function diffCodeBlockRows(look: Appearance): Record<'added' | 'removed' | 'hunk', string> {
  return {
    added: over(TINTS.addition, look.tintAlpha, look.codeBlock),
    removed: over(TINTS.deletion, look.tintAlpha, look.codeBlock),
    hunk: over(TINTS.hunk, look.tintAlpha, look.codeBlock),
  };
}

/** Every pair of a syntax colour and a surface the product can draw it on. */
function drawnPairs(look: Appearance): Drawn[] {
  const rows = diffCodeBlockRows(look);
  const onAnySurface = themeColors(look.theme).flatMap((color) =>
    Object.entries(anyTokenSurfaces(look)).map(([surface, background]) => ({ color, surface, background })),
  );
  return [
    ...onAnySurface,
    { color: colorOfType(look.theme, 'inserted'), surface: 'added row of a diff code block', background: rows.added },
    {
      color: colorOfType(look.theme, 'deleted'),
      surface: 'removed row of a diff code block',
      background: rows.removed,
    },
    { color: toHex(look.theme.plain.color ?? ''), surface: 'hunk row of a diff code block', background: rows.hunk },
  ];
}

describe.each(Object.entries(APPEARANCES))('syntax theme, %s appearance', (_name, look) => {
  it('has every colour at 4.5:1 or more on every surface that can show it', () => {
    expect(
      drawnPairs(look)
        .filter((drawn) => ratioOf(drawn) < MIN_CONTRAST)
        .map(describeDrawn),
    ).toEqual([]);
  });

  it('keeps every stock colour that already reaches 4.5:1 everywhere, so only what falls short is replaced', () => {
    const stock = look.theme === SYNTAX_THEME_LIGHT ? themes.oneLight : themes.oneDark;
    const fallingShort = new Set(
      drawnPairs({ ...look, theme: stock })
        .filter((drawn) => ratioOf(drawn) < MIN_CONTRAST)
        .map((drawn) => drawn.color),
    );
    look.theme.styles.forEach((entry, at) => {
      const original = stock.styles[at]?.style.color;
      if (original !== undefined && !fallingShort.has(toHex(original))) {
        expect(entry.style.color).toBe(original);
      }
    });
  });

  it('leaves the secondary text colour of the line numbers readable on the same surfaces and on the rows of a diff code block', () => {
    const surfaces = { ...anyTokenSurfaces(look), ...diffCodeBlockRows(look) };
    const numbers = Object.entries(surfaces).map(([surface, background]) => ({
      color: over(look.foreground, mutedForegroundAlpha(), background),
      surface,
      background,
    }));
    expect(numbers.filter((drawn) => ratioOf(drawn) < MIN_CONTRAST).map(describeDrawn)).toEqual([]);
  });
});

describe('syntax themes against the stock themes', () => {
  /** A theme's rules with their colours taken out. */
  const withoutColors = (theme: SyntaxTheme) =>
    theme.styles.map(({ style: { color: _color, ...style }, ...rest }) => ({ ...rest, style }));

  it('light: differs from the stock theme in colours only', () => {
    expect(SYNTAX_THEME_LIGHT.plain).toEqual(themes.oneLight.plain);
    expect(withoutColors(SYNTAX_THEME_LIGHT)).toEqual(withoutColors(themes.oneLight));
  });

  it('dark: differs from the stock theme in colours only', () => {
    expect(SYNTAX_THEME_DARK.plain).toEqual(themes.oneDark.plain);
    expect(withoutColors(SYNTAX_THEME_DARK)).toEqual(withoutColors(themes.oneDark));
  });

  it('picks the theme by the resolved appearance, light for anything but dark', () => {
    expect(syntaxThemeFor('dark')).toBe(SYNTAX_THEME_DARK);
    expect(syntaxThemeFor('light')).toBe(SYNTAX_THEME_LIGHT);
    expect(syntaxThemeFor(undefined)).toBe(SYNTAX_THEME_LIGHT);
  });
});
