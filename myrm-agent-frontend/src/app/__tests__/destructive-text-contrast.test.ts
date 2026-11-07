/**
 * [INPUT]
 * src/app/globals.css 全文。
 * [OUTPUT]
 * Vitest: `--destructive-text` 在两套主题里承载文字的每种表面上都 ≥4.5:1，并已声明成 Tailwind 颜色（`text-destructive-text`）。
 * [POS]
 * 防退化守卫：`--destructive` 是实心填充色，作文字时浅色只有 3.8:1、深色在弹层上只有 1.5:1；改动任一表面色
 * 或本令牌，不达标会在这里失败，而不是等到真实页面里才看出来。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBALS_CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

const MIN_TEXT_CONTRAST = 4.5;
/** 危险项的悬停 / 聚焦底：`hover:bg-destructive/10`。 */
const DESTRUCTIVE_TINT = 0.1;
/** 弹层底：`bg-popover/95`。 */
const POPOVER_OPACITY = 0.95;

/** 主题名与声明它的选择器（作正则源码）。 */
const THEMES: ReadonlyArray<readonly [name: string, selector: string]> = [
  ['light', ':root'],
  ['dark', '\\.dark'],
];

type Rgb = readonly [number, number, number];
interface Rgba {
  rgb: Rgb;
  alpha: number;
}

/** 声明了 `--destructive-text` 的那个 `selector { … }` 块（块的结束 `}` 顶格）。 */
function themeBlock(css: string, selector: string): string {
  const blocks = [...css.matchAll(new RegExp(`^${selector}\\s*\\{([\\s\\S]*?)^\\}`, 'gm'))].map((match) => match[1]);
  const block = blocks.find((candidate) => candidate.includes('--destructive-text:'));
  if (block === undefined) {
    throw new Error(`no ${selector} block declares --destructive-text`);
  }
  return block;
}

function declared(block: string, token: string): string {
  const match = new RegExp(`(?<![\\w-])${token}:\\s*([^;]+);`).exec(block);
  if (match === null) {
    throw new Error(`${token} is not declared in the theme block`);
  }
  return match[1];
}

/** 把 `top` 以 `alpha` 的不透明度叠在 `base` 上。 */
function blend(top: Rgb, alpha: number, base: Rgb): Rgb {
  const channel = (i: 0 | 1 | 2): number => top[i] * alpha + base[i] * (1 - alpha);
  return [channel(0), channel(1), channel(2)];
}

function parseColor(value: string, block: string): Rgba {
  const text = value.trim();
  const hex = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(text);
  if (hex !== null) {
    const channel = (start: number): number => parseInt(hex[1].slice(start, start + 2), 16);
    return { rgb: [channel(0), channel(2), channel(4)], alpha: hex[2] === undefined ? 1 : parseInt(hex[2], 16) / 255 };
  }
  const reference = /^var\((--[\w-]+)\)$/.exec(text);
  if (reference !== null) {
    return parseColor(declared(block, reference[1]), block);
  }
  const mix = /^color-mix\(in srgb,\s*(.+?)\s+(\d+)%,\s*(.+?)\s+(\d+)%\)$/.exec(text);
  if (mix !== null) {
    const share = Number(mix[2]) / (Number(mix[2]) + Number(mix[4]));
    return { rgb: blend(parseColor(mix[1], block).rgb, share, parseColor(mix[3], block).rgb), alpha: 1 };
  }
  throw new Error(`unsupported color value: ${text}`);
}

function luminance([r, g, b]: Rgb): number {
  const linear = (channel: number): number => {
    const unit = channel / 255;
    return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** 对比度低于 4.5:1 的 `<主题> <表面> <对比度>`；空数组表示全部达标。 */
function failures(css: string): string[] {
  return THEMES.flatMap(([theme, selector]) => {
    const block = themeBlock(css, selector);
    const color = (token: string): Rgba => parseColor(`var(--${token})`, block);
    const page = color('background').rgb;
    const popover = color('popover').rgb;
    const fill = color('destructive').rgb;
    const surfaces: ReadonlyArray<readonly [string, Rgb]> = [
      ['background', page],
      ['card', color('card').rgb],
      ['popover', popover],
      ['popover/95', blend(popover, POPOVER_OPACITY, page)],
      ['secondary', blend(color('secondary').rgb, color('secondary').alpha, page)],
      ['muted', blend(color('muted').rgb, color('muted').alpha, page)],
      ['accent', blend(color('accent').rgb, color('accent').alpha, page)],
      ['destructive/10 on background', blend(fill, DESTRUCTIVE_TINT, page)],
      ['destructive/10 on popover', blend(fill, DESTRUCTIVE_TINT, popover)],
    ];
    const text = color('destructive-text').rgb;
    return surfaces
      .map(([name, surface]) => ({ name, ratio: contrast(text, surface) }))
      .filter(({ ratio }) => ratio < MIN_TEXT_CONTRAST)
      .map(({ name, ratio }) => `${theme} ${name} ${ratio.toFixed(2)}`);
  });
}

describe('--destructive-text', () => {
  it('reads at least 4.5:1 on every surface that carries text, in both themes', () => {
    expect(failures(GLOBALS_CSS)).toEqual([]);
  });

  it('is declared as a Tailwind color so `text-destructive-text` generates a style', () => {
    expect(GLOBALS_CSS).toMatch(/--color-destructive-text:\s*var\(--destructive-text\);/);
  });

  it.each([
    ['light', /(:root[\s\S]*?--destructive-text:\s*)#c62828/, '#ee4343', 'light popover '],
    ['dark', /(\.dark[\s\S]*?--destructive-text:\s*)#f87171/, '#801d1d', 'dark popover '],
  ])('rejects the %s fill color used as text', (_theme, pattern, fillColor, failurePrefix) => {
    const mutated = GLOBALS_CSS.replace(pattern, `$1${fillColor}`);

    expect(mutated).not.toBe(GLOBALS_CSS);
    expect(failures(mutated).some((failure) => failure.startsWith(failurePrefix))).toBe(true);
  });
});
