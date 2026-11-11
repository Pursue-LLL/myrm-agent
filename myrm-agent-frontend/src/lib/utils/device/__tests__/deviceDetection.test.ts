import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { checkIsMobile } from '../deviceDetection';

const setWidth = (width: number) => vi.stubGlobal('innerWidth', width);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('checkIsMobile', () => {
  it.each([
    [320, true],
    [1023, true],
    [1024, false],
    [1920, false],
  ])('at a window %ipx wide answers %s', (width, mobile) => {
    setWidth(width);

    expect(checkIsMobile()).toBe(mobile);
  });

  it('is never mobile where there is no window to measure, as on the server', () => {
    vi.stubGlobal('window', undefined);

    expect(checkIsMobile()).toBe(false);
  });
});

/**
 * The layout only learns it is mobile after the client mounts, so globals.css hides the wide layout's shell and its
 * left padding below the same width through a plain media query. The two must flip at the same width, or a window in
 * between shows the wrong layout: a sidebar covering a phone, or a wide layout with no navigation at all.
 */
describe('the narrow-window fallback in globals.css', () => {
  const css = readFileSync(resolve(__dirname, '../../../../app/globals.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

  /** Each `@media (max-width: Npx) { ... }` block with its body, found by matching braces. */
  const maxWidthBlocks = Array.from(css.matchAll(/@media \(max-width: (\d+)px\) \{/g)).map((match) => {
    const start = (match.index ?? 0) + match[0].length;
    let depth = 1;
    let end = start;
    while (depth > 0 && end < css.length) {
      depth += css[end] === '{' ? 1 : css[end] === '}' ? -1 : 0;
      end += 1;
    }
    return { maxWidth: Number(match[1]), body: css.slice(start, end - 1) };
  });

  /** The narrowest window the app lays out as wide, read from the detection itself. */
  const narrowestWideWidth = () => {
    for (let width = 1; width <= 4096; width += 1) {
      setWidth(width);
      if (!checkIsMobile()) {
        return width;
      }
    }
    throw new Error('no window width is treated as wide');
  };

  it.each(['.main-content-area', '.wide-layout-only'])(
    'applies %s up to the width just below the mobile layout',
    (selector) => {
      const widths = maxWidthBlocks
        .filter((block) => block.body.includes(`${selector} {`))
        .map((block) => block.maxWidth);

      expect(widths).toEqual([narrowestWideWidth() - 1]);
    },
  );
});
