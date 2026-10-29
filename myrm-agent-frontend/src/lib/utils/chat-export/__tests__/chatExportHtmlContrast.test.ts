import { describe, expect, it } from 'vitest';
import { contrastRatio } from '@/theme-engine/oklch';
import { getHljsTheme, getStyles } from '../chatExportHtmlTemplates';

const MIN_CONTRAST = 4.5;
const THEMES = ['light', 'dark'] as const;
type Theme = (typeof THEMES)[number];

function pick<T>(map: Record<string, T>, key: string): T {
  const value = map[key];
  if (value === undefined) {
    throw new Error(`${key} is not declared`);
  }
  return value;
}

function fullHex(hex: string): string {
  const digits = hex.slice(1);
  return digits.length === 3 ? `#${[...digits].map((d) => d + d).join('')}` : `#${digits}`;
}

function declarations(block: string): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const [, name, value] of block.matchAll(/--([\w-]+):(#[0-9a-fA-F]{3,6})/g)) {
    vars[name as string] = fullHex(value as string);
  }
  return vars;
}

/** The colours of one theme: the `:root` set, with the dark set laid over it for the dark theme. */
function paletteOf(css: string, theme: Theme): Record<string, string> {
  const light = declarations(/:root\{([^}]*)\}/.exec(css)?.[1] ?? '');
  if (theme === 'light') {
    return light;
  }
  return { ...light, ...declarations(/\[data-theme="dark"\]\{([^}]*)\}/.exec(css)?.[1] ?? '') };
}

function toHex(channels: number[]): string {
  return `#${channels.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`;
}

/** A translucent `rgba(r,g,b,a)` laid over an opaque hex surface. */
function over(rgba: string, surface: string): string {
  const parts = /rgba\((\d+),(\d+),(\d+),([\d.]+)\)/.exec(rgba)?.slice(1).map(Number);
  if (parts?.length !== 4) {
    throw new Error(`not an rgba colour: ${rgba}`);
  }
  const alpha = parts[3] as number;
  const under = [1, 3, 5].map((i) => Number.parseInt(surface.slice(i, i + 2), 16));
  return toHex(parts.slice(0, 3).map((c, i) => c * alpha + (under[i] as number) * (1 - alpha)));
}

function overlayOf(css: string, selector: RegExp): string {
  const found = selector.exec(css)?.[1];
  if (!found) {
    throw new Error(`overlay not found for ${selector}`);
  }
  return found;
}

const css = getStyles();
const hljs = getHljsTheme();

describe('exported HTML text stays readable in both themes', () => {
  describe.each(THEMES)('%s', (theme) => {
    const palette = paletteOf(css, theme);
    const codeHeaderOverlay =
      theme === 'light'
        ? /\.code-header\{[^}]*background:(rgba\([^)]*\))/
        : /\[data-theme="dark"\] \.code-header\{background:(rgba\([^)]*\))/;
    const surfaces: Record<string, string> = {
      bg: pick(palette, 'bg'),
      card: pick(palette, 'card'),
      'card-user': pick(palette, 'card-user'),
      'header-bg': pick(palette, 'header-bg'),
      'stats-bg': pick(palette, 'stats-bg'),
      'code-bg': pick(palette, 'code-bg'),
      'code-header': over(overlayOf(css, codeHeaderOverlay), pick(palette, 'code-bg')),
      notice: over(overlayOf(css, /\.redacted-notice\{[^}]*background:(rgba\([^)]*\))/), pick(palette, 'header-bg')),
    };

    const PAIRS: Array<[text: string, onSurfaces: string[]]> = [
      ['fg', ['bg', 'card', 'card-user', 'header-bg', 'stats-bg', 'code-bg', 'code-header']],
      ['muted', ['bg', 'card', 'card-user', 'header-bg', 'stats-bg', 'code-bg', 'code-header']],
      ['accent', ['bg', 'card', 'card-user', 'header-bg', 'stats-bg', 'notice']],
      ['ok', ['code-header']],
      ['danger', ['card', 'card-user']],
    ];

    it.each(PAIRS.flatMap(([text, onSurfaces]) => onSurfaces.map((surface) => [text, surface] as const)))(
      '%s text on %s',
      (text, surface) => {
        const foreground = pick(palette, text);
        const background = pick(surfaces, surface);
        expect(contrastRatio(foreground, background), `${foreground} on ${background}`).toBeGreaterThanOrEqual(
          MIN_CONTRAST,
        );
      },
    );

    it('the model badge text is readable on the accent colour', () => {
      expect(contrastRatio(pick(palette, 'on-accent'), pick(palette, 'accent'))).toBeGreaterThanOrEqual(MIN_CONTRAST);
    });

    it('every syntax colour is readable on the code block', () => {
      const codeBackground = pick(palette, 'code-bg');
      const colours: string[] = [];
      for (const line of hljs.split('\n')) {
        const isDark = line.startsWith('[data-theme="dark"]');
        const colour = /\{color:(#[0-9a-fA-F]{3,6})\}/.exec(line)?.[1];
        if (colour && isDark === (theme === 'dark')) {
          colours.push(fullHex(colour));
        }
      }
      expect(colours.length).toBeGreaterThan(0);
      for (const colour of colours) {
        expect(contrastRatio(colour, codeBackground), `${colour} on ${codeBackground}`).toBeGreaterThanOrEqual(
          MIN_CONTRAST,
        );
      }
    });
  });

  it('takes every text colour from the theme variables, so the checks above cover it', () => {
    const screenStyles = css.replace(/@media print\{[\s\S]*\}\s*$/, '');
    const literals = [...screenStyles.matchAll(/(?<![-\w])color:(?!var\(--)([^;}]+)/g)].map((m) => m[1]);

    expect(literals).toEqual([]);
  });
});
