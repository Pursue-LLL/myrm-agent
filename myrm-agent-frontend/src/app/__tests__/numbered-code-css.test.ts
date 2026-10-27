/**
 * [INPUT]
 * src/app/globals.css 与 src/app/numbered-code.css 全文。
 * [OUTPUT]
 * Vitest: 行号代码视图依赖的样式合约存在（CSS 计数器行号、不可选中、按行跳过离屏渲染），且被全局样式引入。
 * [POS]
 * 防退化守卫：LineNumberedCode 的行号完全由 CSS 生成，样式文件漏引入或计数器被改掉时，组件测试（jsdom 不渲染生成内容）发现不了，
 * 用户看到的是一个没有行号的文件；行号一旦写进 DOM 又会被选中复制进文件内容。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const read = (file: string): string => readFileSync(resolve(process.cwd(), 'src/app', file), 'utf8');

describe('numbered code stylesheet', () => {
  const css = read('numbered-code.css');

  it('is part of the global stylesheet', () => {
    expect(read('globals.css')).toContain("@import './numbered-code.css';");
  });

  it('counts the rows with a CSS counter and draws the number as generated content', () => {
    expect(css).toMatch(/\.numbered-code\s*\{[^}]*counter-reset:\s*numbered-line/);
    expect(css).toMatch(/\.numbered-code-line\s*\{[^}]*counter-increment:\s*numbered-line/);
    expect(css).toMatch(/\.numbered-code-line::before\s*\{[^}]*content:\s*counter\(numbered-line\)/);
  });

  it('keeps the number out of selection and out of the accessibility tree', () => {
    const before = css.match(/\.numbered-code-line::before\s*\{([^}]*)\}/)?.[1] ?? '';
    expect(before).toMatch(/user-select:\s*none/);
    expect(before).toMatch(/content:\s*counter\(numbered-line\)\s*\/\s*''/);
  });

  it("draws the number in the theme's secondary text colour, which stays readable on both themes", () => {
    const before = css.match(/\.numbered-code-line::before\s*\{([^}]*)\}/)?.[1] ?? '';
    expect(before).toMatch(/color:\s*var\(--muted-foreground\);/);
  });

  it('lets the browser skip off-screen rows of long files only, and remember the height of rows it has seen', () => {
    expect(css).toMatch(/\.numbered-code-lazy\s*>\s*\.numbered-code-line\s*\{[^}]*content-visibility:\s*auto/);
    expect(css).toMatch(/\.numbered-code-lazy\s*>\s*\.numbered-code-line\s*\{[^}]*contain-intrinsic-size:\s*auto/);
    const plainRow = css.match(/\.numbered-code-line\s*\{([^}]*)\}/)?.[1] ?? '';
    expect(plainRow).not.toContain('content-visibility');
  });
});
