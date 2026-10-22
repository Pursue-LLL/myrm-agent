// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
  findUndefinedSemanticColorSites,
  findWrappedThemeColorSites,
  isCompleteColorValue,
  parseDeclaredColorTokens,
} from '../theme-color-scan';

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

describe('parseDeclaredColorTokens', () => {
  it('collects every --color-* declaration of the theme block', () => {
    const css =
      '@theme {\n  --color-primary: var(--primary);\n  --color-warning-foreground:var(--warning-foreground);\n}';
    expect([...parseDeclaredColorTokens(css)].sort()).toEqual(['primary', 'warning-foreground']);
  });

  it('ignores plain theme variables that Tailwind does not turn into colour utilities', () => {
    expect([...parseDeclaredColorTokens(':root { --warning: #915c00; --radius: 8px; }')]).toEqual([]);
  });
});

describe('findUndefinedSemanticColorSites', () => {
  const declared = new Set(['primary', 'warning']);
  const tokens = (source: string): string[] =>
    findUndefinedSemanticColorSites(source, declared).map((site) => site.token);

  it('flags a semantic colour utility whose --color-* token is not declared', () => {
    expect(tokens(`className="bg-success/10 text-success"`)).toEqual(['success', 'success']);
    expect(tokens(`'hover:bg-info dark:border-danger'`)).toEqual(['info', 'danger']);
    expect(tokens(`'from-primary to-error'`)).toEqual(['error']);
  });

  it('treats the foreground token as its own declaration', () => {
    expect(tokens(`className="text-warning-foreground"`)).toEqual(['warning-foreground']);
    expect(findUndefinedSemanticColorSites(`text-warning-foreground`, new Set(['warning-foreground']))).toEqual([]);
  });

  it('accepts declared tokens, with opacity modifiers and variants', () => {
    expect(tokens(`className="bg-warning/10 border-warning/30 text-warning dark:text-warning"`)).toEqual([]);
  });

  it('does not mistake ordinary words or non-colour utilities for semantic colours', () => {
    expect(tokens(`seek-to-error and go-to-info`)).toEqual([]);
    expect(tokens(`className="text-xs bg-cover border-dashed text-warning-light"`)).toEqual([]);
  });

  it('reports the 1-based line and the matched class text', () => {
    const sites = findUndefinedSemanticColorSites(['a', `b: 'bg-error/20'`].join('\n'), declared);
    expect(sites).toEqual([{ line: 2, text: 'bg-error', token: 'error' }]);
  });
});
