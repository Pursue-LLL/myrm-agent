// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findWrappedThemeColorSites, isCompleteColorValue } from '../theme-color-scan';

const texts = (source: string): string[] => findWrappedThemeColorSites(source).map((site) => site.text);

describe('findWrappedThemeColorSites', () => {
  it('flags a theme variable wrapped as the whole colour of hsl / hsla / rgb / rgba', () => {
    expect(texts(`stroke="hsl(var(--primary))"`)).toEqual(['hsl(var(--primary)']);
    expect(texts(`stroke="rgb(var(--primary))"`)).toEqual(['rgb(var(--primary)']);
    expect(texts(`color: hsla(var(--primary))`)).toEqual(['hsla(var(--primary)']);
    expect(texts(`color: rgba(var(--primary))`)).toEqual(['rgba(var(--primary)']);
  });

  it('flags the alpha forms that still treat the variable as a whole colour', () => {
    expect(texts(`background-color: hsl(var(--primary) / 0.2);`)).toEqual(['hsl(var(--primary)']);
    expect(texts(`box-shadow: 0 0 0 2px rgba(var(--primary), 0.2);`)).toEqual(['rgba(var(--primary)']);
    expect(texts(`'shadow-[0_0_8px_hsl(var(--primary)/0.55)]'`)).toEqual(['hsl(var(--primary)']);
    expect(texts(`'focus:shadow-[0_0_0_4px_rgba(var(--primary),0.1)]'`)).toEqual(['rgba(var(--primary)']);
  });

  it('reports the 1-based line of every match, several per line included', () => {
    const source = ['const ok = 1;', `a: 'hsl(var(--a))', b: 'rgb(var(--b))'`, '', `c: 'hsl(var(--c))'`].join('\n');
    expect(findWrappedThemeColorSites(source).map((site) => site.line)).toEqual([2, 2, 4]);
  });

  it('accepts the supported spellings', () => {
    expect(texts(`stroke="var(--primary)"`)).toEqual([]);
    expect(texts(`fill: color-mix(in srgb, var(--primary) 20%, transparent)`)).toEqual([]);
    expect(texts(`stroke="var(--color-emerald-600, #059669)"`)).toEqual([]);
    expect(texts(`className="shadow-primary/20 bg-primary/10"`)).toEqual([]);
  });

  it('accepts a variable that is only a colour channel or carries a triplet fallback', () => {
    expect(texts(`color: hsl(var(--agent-hue) 58% 48%)`)).toEqual([]);
    expect(texts(`color: hsl(var(--agent-hue) 50% 50% / 12%)`)).toEqual([]);
    expect(texts(`color: hsl(var(--x, 217 91% 60%))`)).toEqual([]);
  });

  it('exempts the widget bridge variables that carry triplets inside the iframe', () => {
    expect(texts(`border: 2px solid hsl(var(--widget-primary, 217 91% 60%))`)).toEqual([]);
    expect(texts(`background: hsla(var(--widget-primary))`)).toEqual([]);
  });
});

describe('isCompleteColorValue', () => {
  it('accepts complete colours', () => {
    expect(isCompleteColorValue('#6799a0')).toBe(true);
    expect(isCompleteColorValue(' #fbfbf8cf ')).toBe(true);
    expect(isCompleteColorValue('oklch(0.6 0.1 200)')).toBe(true);
    expect(isCompleteColorValue('hsl(210 40% 50%)')).toBe(true);
  });

  it('rejects a bare channel triplet, which is the one format where wrapping would be correct', () => {
    expect(isCompleteColorValue('210 40% 50%')).toBe(false);
    expect(isCompleteColorValue('103, 153, 160')).toBe(false);
    expect(isCompleteColorValue('')).toBe(false);
  });
});
